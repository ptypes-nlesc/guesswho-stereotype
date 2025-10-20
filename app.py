import datetime
import json
import os
import random
import sqlite3
import uuid

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, join_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

LOG_FILE = "data/game_log.json"  # legacy JSON audit file (no longer written by default)
DB_PATH = "db/games.db"


# ---utility logging
def log_turn(entry):
    """Append a new entry to the JSON log file, handling empty file safely."""
    # ensure timestamp
    entry["timestamp"] = datetime.datetime.now().isoformat()

    # Persist to SQLite as canonical store
    try:
        db_log_event(entry)
    except Exception as e:
        print(f"DEBUG: failed to write event to DB: {e}")

    # Legacy JSON audit file is no longer written by default. If you want the
    # human-readable append log, re-enable the JSON write here.


# ---cards-setup (auto-generate from 1-12)
CARDS = [{"id": i, "name": f"Card {i}"} for i in range(1, 13)]


# --- SQLite helpers and per-game persistence
def get_db_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            chosen_card INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT,
            role TEXT,
            action TEXT,
            text TEXT,
            card INTEGER,
            timestamp TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eliminated_cards (
            game_id TEXT,
            card_id INTEGER,
            eliminated_at TEXT,
            PRIMARY KEY(game_id, card_id)
        )
        """
    )
    conn.commit()
    conn.close()


def create_game(game_id=None):
    """Create a new game with a random chosen card and return the game id and chosen card id."""
    if game_id is None:
        game_id = uuid.uuid4().hex
    chosen_card = random.choice(CARDS)["id"]
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO games (id, created_at, chosen_card) VALUES (?, ?, ?)",
        (game_id, datetime.datetime.now().isoformat(), chosen_card),
    )
    # Clear eliminated cards for this game when starting a new/updated game
    cur.execute("DELETE FROM eliminated_cards WHERE game_id = ?", (game_id,))
    conn.commit()
    conn.close()
    # log the card draw as a system event
    log_turn({"role": "system", "action": "card_draw", "card": chosen_card, "game_id": game_id})
    return game_id, chosen_card


def db_log_event(entry):
    game_id = entry.get("game_id", "default")
    role = entry.get("role")
    action = entry.get("action")
    # Ignore transient UI-only events — do not persist these research-unimportant events
    if action in ("question", "answer", "note"):
        # keep a minimal debug trace on server stdout, but don't insert into DB
        print(f"DEBUG: skipping persistence for action={action} (game={game_id})")
        return
    text = entry.get("text") or entry.get("note") or entry.get("question") or entry.get("answer")
    card = None
    if "card" in entry:
        try:
            card = int(entry.get("card"))
        except Exception:
            card = None

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (game_id, role, action, text, card, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (game_id, role, action, text, card, entry.get("timestamp")),
    )
    # if elimination, record eliminated_cards table for easy counting
    if action == "eliminate" and card is not None:
        cur.execute(
            "INSERT OR REPLACE INTO eliminated_cards (game_id, card_id, eliminated_at) VALUES (?, ?, ?)",
            (game_id, card, entry.get("timestamp")),
        )
    conn.commit()
    conn.close()


def get_transcript_from_db(game_id="default", limit=200):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM events WHERE game_id = ? ORDER BY id DESC LIMIT ?",
        (game_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    # return as list oldest->newest
    out = [dict(r) for r in reversed(rows)]
    return out


def get_eliminated_for_game(game_id="default"):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT card_id FROM eliminated_cards WHERE game_id = ?", (game_id,))
    rows = cur.fetchall()
    conn.close()
    return {r[0] for r in rows}


def get_chosen_card(game_id="default"):
    conn = get_db_conn()
    cur = conn.cursor()
    # First try the games table
    cur.execute("SELECT chosen_card FROM games WHERE id = ?", (game_id,))
    r = cur.fetchone()
    if r and r[0] is not None:
        conn.close()
        return r[0]

    # Fallback: use the most recent card_draw event for this game (if any)
    cur.execute(
        "SELECT card FROM events WHERE game_id = ? AND action = 'card_draw' ORDER BY id DESC LIMIT 1",
        (game_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0]
    return None


# ensure DB exists and a default game is present
init_db()
_default_game_id, _ = create_game("default")

LAST_UPDATE = 0


# ---routes for game screens
@app.route("/player1")
def player1():
    game_id = request.args.get('game_id', 'default')
    chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
    return render_template("player1.html", card={"id": chosen, "name": f"Card {chosen}"}, game_id=game_id)


@app.route("/player2")
def player2():
    game_id = request.args.get('game_id', 'default')
    eliminated = get_eliminated_for_game(game_id)
    print(f"DEBUG: ELIMINATED_CARDS for {game_id} = {eliminated}")  # Debug output
    return render_template("player2.html", cards=CARDS, eliminated=eliminated, game_id=game_id)


@app.route("/moderator")
def moderator():
    return render_template("moderator.html")


# API endpoints are implemented primarily via Socket.IO events now. The
# /submit_question, /submit_answer and /submit_note HTTP endpoints were removed
# because the UI no longer exposes direct controls for them. Socket events
# ('question','answer','note','chat','eliminate') remain supported for real-time
# communication.


# --- Socket event handlers
@socketio.on('join')
def handle_join(data):
    """Client asks to join a game room. data should contain game_id."""
    game_id = data.get('game_id', 'default')
    room = f"game:{game_id}"
    join_room(room)
    # Debug log
    print(f"DEBUG: socket joined room {room}")
    # Optionally notify room that someone joined
    # emit only to the room that was just joined
    socketio.emit('system', {'action': 'join', 'room': room}, to=room)


@socketio.on('connect')
def handle_connect():
    sid = request.sid if hasattr(request, 'sid') else None
    print(f"DEBUG: client connected sid={sid}")


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid if hasattr(request, 'sid') else None
    print(f"DEBUG: client disconnected sid={sid}")


@socketio.on('chat')
def handle_chat(data):
    """Receive chat from a client, persist it, and broadcast to the room.

    Expected data: { game_id, role, text }
    """
    game_id = data.get('game_id', 'default')
    room = f"game:{game_id}"
    payload = {
        'role': data.get('role', 'unknown'),
        'action': 'chat',
        'text': data.get('text', ''),
        'game_id': game_id,
    }
    # persist on disk for research audit
    log_turn(payload)
    # Debug log
    print(f"DEBUG: chat from {payload.get('role')} in game {game_id}: {payload.get('text')}")
    # broadcast to all connected clients (room-based delivery may miss clients who haven't joined yet)
    socketio.emit('chat', payload, to=room)


@app.route('/submit_chat', methods=['POST'])
def submit_chat():
    """HTTP fallback for submitting chat (also logs and emits to room)."""
    data = request.get_json(silent=True) or {}
    game_id = data.get('game_id', 'default')
    room = f"game:{game_id}"
    payload = {
        'role': data.get('role', 'unknown'),
        'action': 'chat',
        'text': data.get('text', ''),
        'game_id': game_id,
    }
    log_turn(payload)
    print(f"DEBUG: HTTP chat fallback from {payload.get('role')} in game {game_id}: {payload.get('text')}")
    socketio.emit('chat', payload, to=room)
    return jsonify({'status': 'ok'})


# (submit_answer removed)


@app.route("/eliminate_card", methods=["POST"])
def eliminate_card():
    global LAST_UPDATE
    data = request.get_json(silent=True) or {}
    cid = data.get("card_id")
    if cid is None:
        return jsonify({"status": "error", "message": "card_id is required"}), 400
    game_id = data.get('game_id', 'default')
    LAST_UPDATE = datetime.datetime.now().timestamp()  # Update timestamp
    payload = {"role": "player2", "action": "eliminate", "card": cid, "game_id": game_id}
    log_turn(payload)
    # fetch eliminated set from DB after logging
    eliminated = get_eliminated_for_game(game_id)
    print(f"DEBUG: Eliminated card {cid} for game {game_id}, eliminated now = {eliminated}")  # Debug
    # let all clients in the room know which card was eliminated
    try:
        cid_int = int(cid)
    except Exception:
        return jsonify({"status": "error", "message": "card_id must be an integer"}), 400
    socketio.emit('eliminate', {"card": cid_int, "eliminated": list(eliminated), **payload}, to=f"game:{game_id}")
    return jsonify({"status": "ok"})



@app.route('/create_game', methods=['POST'])
def create_game(game_id=None):
    """Create a new game with a random chosen card and return the game id and chosen card id.

    This function is intentionally non-destructive: it will create a new games row
    and persist a `card_draw` system event for auditing. It will not delete any prior
    events or eliminated_cards for other game ids.
    """
    # If no id requested, generate a unique id
    conn = get_db_conn()
    cur = conn.cursor()
    if game_id is None:
        # generate a random uuid hex; it's practically unique so no need to loop
        game_id = uuid.uuid4().hex

    # If a caller provided a game_id that already exists, fail to avoid accidental overwrite.
    cur.execute("SELECT 1 FROM games WHERE id = ?", (game_id,))
    if cur.fetchone() is not None:
        conn.close()
        raise ValueError(f"game_id '{game_id}' already exists")

    chosen_card = random.choice(CARDS)["id"]
    # Insert a new games row. Do NOT delete prior events or eliminated_cards for any game id.
    cur.execute(
        "INSERT INTO games (id, created_at, chosen_card) VALUES (?, ?, ?)",
        (game_id, datetime.datetime.now().isoformat(), chosen_card),
    )
    conn.commit()
    conn.close()

    # Log the card draw as a system event so the chosen card is recorded in the DB.
    # The client UI intentionally hides system messages (role=='system'), so this will
    # not appear in the chat transcript visible to users, but remains in the audit log.
    try:
        log_turn({"role": "system", "action": "card_draw", "card": chosen_card, "game_id": game_id})
    except Exception as e:
        print(f"DEBUG: failed to log card_draw for game {game_id}: {e}")
    return game_id, chosen_card

@app.route('/transcript')
def transcript():
    """Return recent transcript events for a game.

    Query params:
      game_id (optional): filter by game id (default: 'default')
      limit (optional): max number of items to return (default: 200)
    """
    game_id = request.args.get('game_id', 'default')
    try:
        limit = int(request.args.get('limit', '200'))
    except ValueError:
        limit = 200

    # Prefer DB-backed transcript
    try:
        result = get_transcript_from_db(game_id, limit)
        return jsonify(result)
    except Exception:
        # fallback to JSON file (backwards compatible)
        if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
            return jsonify([])
        try:
            with open(LOG_FILE, 'r') as f:
                data = json.load(f)
        except Exception:
            return jsonify([])

        filtered = [e for e in data if (
            e.get('game_id') == game_id or e.get('role') == 'system' or e.get('action') in ('chat','question','answer','eliminate','note')
        )]
        return jsonify(filtered[-limit:])


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    # Use Socket.IO runner so websocket clients work in development
    # Disable Flask's reloader to avoid duplicate processes which can cause socket clients
    # to disconnect/reconnect frequently during development. Use a dedicated launcher
    # if you need automatic reloads.
    socketio.run(app, debug=True, use_reloader=False)
