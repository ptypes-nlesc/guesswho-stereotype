import datetime
import json
import os
import random
import sqlite3
import uuid
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, join_room

# ---------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

LOG_FILE = "data/game_log.json"
DB_PATH = "db/games.db"

# 12 cards total
CARDS = [{"id": i, "name": f"Card {i}"} for i in range(1, 13)]


# ---------------------------------------------------------------------
# Database utilities
# ---------------------------------------------------------------------
def get_db_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Ensure tables exist before game starts."""
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                chosen_card INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                role TEXT,
                action TEXT,
                text TEXT,
                card INTEGER,
                timestamp TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS eliminated_cards (
                game_id TEXT,
                card_id INTEGER,
                eliminated_at TEXT,
                PRIMARY KEY(game_id, card_id)
            )
        """)
        conn.commit()


def db_log_event(entry):
    """Insert a structured event into the database."""
    game_id = entry.get("game_id", "default")
    role = entry.get("role", "unknown")
    action = entry.get("action")
    text = (
        entry.get("text")
        or entry.get("note")
        or entry.get("question")
        or entry.get("answer")
    )
    card = None

    if "card" in entry:
        try:
            card = int(entry.get("card"))
        except Exception:
            pass

    # Skip transient UI-only events
    if action in ("question", "answer", "note"):
        print(f"DEBUG: skipped transient action={action} for game={game_id}")
        return

    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO events (game_id, role, action, text, card, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, role, action, text, card, entry.get("timestamp")),
        )

        # Record eliminated cards separately for tracking
        if action == "eliminate" and card is not None:
            cur.execute(
                "INSERT OR REPLACE INTO eliminated_cards (game_id, card_id, eliminated_at) VALUES (?, ?, ?)",
                (game_id, card, entry.get("timestamp")),
            )
        conn.commit()


def get_transcript_from_db(game_id, limit=200):
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM events WHERE game_id = ? ORDER BY id DESC LIMIT ?",
            (game_id, limit),
        )
        rows = cur.fetchall()
        return [dict(r) for r in reversed(rows)]


def get_eliminated_for_game(game_id):
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT card_id FROM eliminated_cards WHERE game_id = ?", (game_id,)
        )
        return {r[0] for r in cur.fetchall()}


def get_chosen_card(game_id):
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chosen_card FROM games WHERE id = ?", (game_id,))
        row = cur.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------
# Initialize DB + default game
# ---------------------------------------------------------------------
init_db()
_default_game_id = uuid.uuid4().hex
with get_db_conn() as conn:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO games (id, created_at, chosen_card) VALUES (?, ?, ?)",
        (
            _default_game_id,
            datetime.datetime.now().isoformat(),
            random.choice(CARDS)["id"],
        ),
    )
    conn.commit()
LAST_UPDATE = 0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def log_turn(entry):
    entry["timestamp"] = datetime.datetime.now().isoformat()
    try:
        db_log_event(entry)
    except Exception as e:
        print(f"DEBUG: DB log failed: {e}")


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.route("/")
def index():
    """Landing page (can later show 'create game' button)."""
    return render_template("index.html")


@app.route("/player1")
def player1():
    """Player 1 (secret card)."""
    game_id = request.args.get("game_id", _default_game_id)
    chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
    return render_template(
        "player1.html", card={"id": chosen, "name": f"Card {chosen}"}, game_id=game_id
    )


@app.route("/player2")
def player2():
    """Player 2 (guesser)."""
    game_id = request.args.get("game_id", _default_game_id)
    eliminated = get_eliminated_for_game(game_id)
    return render_template(
        "player2.html", cards=CARDS, eliminated=eliminated, game_id=game_id
    )


@app.route("/moderator")
def moderator():
    """Moderator view (sees both players)."""
    game_id = request.args.get("game_id", _default_game_id)
    return render_template("moderator.html", game_id=game_id)


# ---------------------------------------------------------------------
# Create new game (API)
# ---------------------------------------------------------------------
@app.route("/create_game", methods=["POST"])
def create_game():
    """Create a new unique game and return ID + chosen card."""
    game_id = uuid.uuid4().hex
    chosen_card = random.choice(CARDS)["id"]

    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO games (id, created_at, chosen_card) VALUES (?, ?, ?)",
            (game_id, datetime.datetime.now().isoformat(), chosen_card),
        )
        conn.commit()

    log_turn(
        {
            "role": "system",
            "action": "card_draw",
            "card": chosen_card,
            "game_id": game_id,
        }
    )
    print(f"DEBUG: new game created {game_id} with card {chosen_card}")
    return jsonify({"status": "ok", "game_id": game_id, "chosen_card": chosen_card})


# ---------------------------------------------------------------------
# Eliminate card (Player2 action)
# ---------------------------------------------------------------------
@app.route("/eliminate_card", methods=["POST"])
def eliminate_card():
    global LAST_UPDATE
    data = request.get_json(silent=True) or {}
    card_id = data.get("card_id")
    game_id = data.get("game_id", _default_game_id)

    if not card_id:
        return jsonify({"status": "error", "message": "card_id required"}), 400

    LAST_UPDATE = datetime.datetime.now().timestamp()
    payload = {
        "role": "player2",
        "action": "eliminate",
        "card": card_id,
        "game_id": game_id,
    }
    log_turn(payload)

    eliminated = get_eliminated_for_game(game_id)
    socketio.emit(
        "eliminate",
        {"card": int(card_id), "eliminated": list(eliminated)},
        to=f"game:{game_id}",
    )
    print(f"DEBUG: eliminated card {card_id} for game {game_id}")
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------
# Socket.IO events
# ---------------------------------------------------------------------
@socketio.on("join")
def handle_join(data):
    """Client joins a specific game room."""
    game_id = data.get("game_id", _default_game_id)
    role = data.get("role", "unknown")
    room = f"game:{game_id}"
    join_room(room)
    print(f"DEBUG: {role} joined {room}")
    socketio.emit(
        "system", {"action": "join", "role": role, "game_id": game_id}, to=room
    )


@socketio.on("chat")
def handle_chat(data):
    """Handle chat messages between roles."""
    game_id = data.get("game_id", _default_game_id)
    room = f"game:{game_id}"
    payload = {
        "role": data.get("role", "unknown"),
        "action": "chat",
        "text": data.get("text", ""),
        "game_id": game_id,
    }
    log_turn(payload)
    socketio.emit("chat", payload, to=room)
    print(f"DEBUG: chat from {payload['role']} in {room}: {payload['text']}")


# ---------------------------------------------------------------------
# Transcript (API)
# ---------------------------------------------------------------------
@app.route("/transcript")
def transcript():
    game_id = request.args.get("game_id", _default_game_id)
    limit = int(request.args.get("limit", "200"))
    result = get_transcript_from_db(game_id, limit)
    return jsonify(result)


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    socketio.run(app, debug=True, use_reloader=False)
