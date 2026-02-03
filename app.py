import datetime
import os
import random
import sqlite3
import uuid
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    redirect,
    url_for,
)
from flask_socketio import SocketIO, join_room

# ---------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "change_this_to_something_secret"),
    TEMPLATES_AUTO_RELOAD=True,
)
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = "db/games.db"
MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD", "research123")

# Card catalog (12 cards)
CARDS = [{"id": i, "name": f"Card {i}"} for i in range(1, 13)]

# Track active voice participants per game: {game_id: {client_id: {role, socket_id}}}
VOICE_PARTICIPANTS = {}

# Role binding store: {(game_id, participant_id): role}
PARTICIPANT_ROLES = {}


# ---------------------------------------------------------------------
# Database utilities
# ---------------------------------------------------------------------
def get_db_conn():
    """Open SQLite connection, creating folder if needed."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Ensure all tables exist before running the app."""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                chosen_card INTEGER
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                role TEXT,
                action TEXT,
                text TEXT,
                card INTEGER,
                participant_id TEXT,
                timestamp TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS eliminated_cards (
                game_id TEXT,
                card_id INTEGER,
                eliminated_at TEXT,
                PRIMARY KEY (game_id, card_id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                role TEXT,
                start_time TEXT,
                end_time TEXT,
                duration_seconds REAL,
                audio_path TEXT,
                transcript TEXT,
                timestamp TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS participant_bindings (
                game_id TEXT,
                participant_id TEXT,
                role TEXT,
                created_at TEXT,
                PRIMARY KEY (game_id, participant_id)
            )
            """
        )
        conn.commit()


def log_event(entry):
    """Insert structured event into DB."""
    game_id = entry.get("game_id", "default")
    role = entry.get("role", "unknown")
    action = entry.get("action", "")
    text = entry.get("text") or ""
    card = entry.get("card")

    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO events (game_id, role, action, text, card, participant_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                game_id,
                role,
                action,
                text,
                card,
                entry.get("participant_id"),
                entry.get("timestamp") or datetime.datetime.now().isoformat(),
            ),
        )

        # Track eliminated cards
        if action == "eliminate" and card is not None:
            c.execute(
                """
                INSERT OR REPLACE INTO eliminated_cards (game_id, card_id, eliminated_at)
                VALUES (?, ?, ?)
                """,
                (game_id, card, datetime.datetime.now().isoformat()),
            )
        conn.commit()


def get_eliminated_cards(game_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT card_id FROM eliminated_cards WHERE game_id = ?", (game_id,))
        return {row[0] for row in c.fetchall()}


def get_chosen_card(game_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT chosen_card FROM games WHERE id = ?", (game_id,))
        row = c.fetchone()
        return row[0] if row else None


def get_transcript(game_id, limit=200):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM events WHERE game_id = ? ORDER BY id DESC LIMIT ?",
            (game_id, limit),
        )
        return [dict(r) for r in reversed(c.fetchall())]


def get_joined_roles(game_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT DISTINCT role FROM events WHERE game_id = ? AND action = ?",
            (game_id, "join"),
        )
        return {row[0] for row in c.fetchall()}


# ---------------------------------------------------------------------
# Initialize DB and default game
# ---------------------------------------------------------------------
init_db()
DEFAULT_GAME_ID = uuid.uuid4().hex
with get_db_conn() as conn:
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO games (id, created_at, chosen_card) VALUES (?, ?, ?)",
        (
            DEFAULT_GAME_ID,
            datetime.datetime.now().isoformat(),
            random.choice(CARDS)["id"],
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------
def record_event(role, action, game_id, text=None, card=None, participant_id=None):
    entry = {
        "role": role,
        "action": action,
        "text": text,
        "card": card,
        "game_id": game_id,
        "participant_id": participant_id,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    try:
        log_event(entry)
    except Exception as e:
        print(f"DB log failed: {e}")


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.route("/")
def index():
    """Moderator login page."""
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    """Simple moderator login."""
    if request.form.get("password") == MODERATOR_PASSWORD:
        session["moderator"] = True
        return redirect(url_for("dashboard"))
    return render_template("index.html", error=True)


@app.route("/logout")
def logout():
    """Clear session and return to login."""
    session.clear()
    return redirect(url_for("index"))


def get_participant_binding(game_id, participant_id):
    """Retrieve role binding from database."""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT role FROM participant_bindings WHERE game_id = ? AND participant_id = ?",
            (game_id, participant_id),
        )
        row = c.fetchone()
        return row[0] if row else None


def set_participant_binding(game_id, participant_id, role):
    """Store role binding in database."""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (?, ?, ?, ?)",
            (game_id, participant_id, role, datetime.datetime.now().isoformat()),
        )
        conn.commit()


# Helper to check role binding (now DB-backed)
def check_role_binding(game_id, participant_id, required_role):
    """
    Enforce role binding: verify participant_id is bound to required_role.
    Source of truth is the database. Creates binding on first route access.
    Returns (allowed: bool, message: str or None)
    """
    if not participant_id:
        return True, None  # No participant_id — allow (backward compat)
    
    # Check DB for existing binding
    bound_role = get_participant_binding(game_id, participant_id)
    
    if bound_role:
        # Binding exists
        if bound_role != required_role:
            return False, f"Forbidden: participant is bound to {bound_role}, not {required_role}"
    else:
        # First access: create binding in DB
        set_participant_binding(game_id, participant_id, required_role)
    
    return True, None


@app.route("/dashboard")
def dashboard():
    """Moderator dashboard."""
    if not session.get("moderator"):
        return redirect(url_for("index"))
    return render_template("dashboard.html")


@app.route("/player1")
def player1():
    """Player 1 – secret card view."""
    game_id = request.args.get("game_id", DEFAULT_GAME_ID)
    participant_id = request.args.get("participant_id")
    
    # Enforce role binding
    allowed, message = check_role_binding(game_id, participant_id, "player1")
    if not allowed:
        return message, 403
    
    chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
    return render_template(
        "player1.html", card={"id": chosen, "name": f"Card {chosen}"}, game_id=game_id
    )


@app.route("/player2")
def player2():
    """Player 2 – guesser grid view."""
    game_id = request.args.get("game_id", DEFAULT_GAME_ID)
    participant_id = request.args.get("participant_id")
    
    # Enforce role binding
    allowed, message = check_role_binding(game_id, participant_id, "player2")
    if not allowed:
        return message, 403
    
    eliminated = get_eliminated_cards(game_id)
    return render_template(
        "player2.html", cards=CARDS, eliminated=eliminated, game_id=game_id
    )


@app.route("/moderator")
def moderator():
    """Moderator live view."""
    game_id = request.args.get("game_id", DEFAULT_GAME_ID)
    participant_id = request.args.get("participant_id")
    
    # Enforce role binding
    allowed, message = check_role_binding(game_id, participant_id, "moderator")
    if not allowed:
        return message, 403

    chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
    eliminated = get_eliminated_cards(game_id)
    return render_template(
        "moderator.html",
        game_id=game_id,
        cards=CARDS,
        eliminated=eliminated,
        secret_card={"id": chosen, "name": f"Card {chosen}"},
    )


@app.route("/create_game", methods=["POST"])
def create_game():
    """Create a new game and return its ID with participant_ids for each role."""
    game_id = uuid.uuid4().hex
    chosen_card = random.choice(CARDS)["id"]
    
    # Generate unique participant_ids for each role
    player1_id = str(uuid.uuid4())
    player2_id = str(uuid.uuid4())
    moderator_id = str(uuid.uuid4())

    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO games (id, created_at, chosen_card) VALUES (?, ?, ?)",
            (game_id, datetime.datetime.now().isoformat(), chosen_card),
        )
        # Pre-bind participant_ids to roles in DB
        c.execute(
            "INSERT INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (?, ?, ?, ?)",
            (game_id, player1_id, "player1", datetime.datetime.now().isoformat()),
        )
        c.execute(
            "INSERT INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (?, ?, ?, ?)",
            (game_id, player2_id, "player2", datetime.datetime.now().isoformat()),
        )
        c.execute(
            "INSERT INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (?, ?, ?, ?)",
            (game_id, moderator_id, "moderator", datetime.datetime.now().isoformat()),
        )
        conn.commit()

    record_event("system", "card_draw", game_id, card=chosen_card)
    print(f"Created new game {game_id} with card {chosen_card}")
    return jsonify({
        "status": "ok",
        "game_id": game_id,
        "chosen_card": chosen_card,
        "participant_ids": {
            "player1": player1_id,
            "player2": player2_id,
            "moderator": moderator_id
        }
    })


@app.route("/eliminate_card", methods=["POST"])
def eliminate_card():
    """Player 2 eliminates a card."""
    data = request.get_json(silent=True) or {}
    card_id = data.get("card_id")
    game_id = data.get("game_id", DEFAULT_GAME_ID)
    if not card_id:
        return jsonify({"status": "error", "message": "card_id required"}), 400

    # Check if card is already eliminated
    eliminated = get_eliminated_cards(game_id)
    if int(card_id) in eliminated:
        return jsonify({"status": "ok"})  # Already eliminated, no action needed

    record_event("player2", "eliminate", game_id, card=card_id)
    socketio.emit(
        "eliminate",
        {"card": int(card_id)},
        to=f"game:{game_id}",
    )
    print(f"Game {game_id}: card {card_id} eliminated")
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------
# Socket.IO events
# Helper to validate role binding on socket events
def validate_role_binding(game_id, participant_id, claimed_role):
    """
    Enforce role binding: verify that participant_id matches the claimed role.
    Returns (valid: bool, error_msg: str or None)
    """
    if not participant_id:
        return True, None  # No participant_id provided — allow (backward compat)
    
    key = (game_id, participant_id)
    if key in PARTICIPANT_ROLES:
        bound_role = PARTICIPANT_ROLES[key]
        if bound_role != claimed_role:
            return False, f"Role mismatch: participant bound to {bound_role}, not {claimed_role}"
    
    return True, None


# ---------------------------------------------------------------------
@socketio.on("join")
def handle_join(data):
    """Clients join a shared room by game ID."""
    game_id = data.get("game_id", DEFAULT_GAME_ID)
    role = data.get("role", "unknown")
    participant_id = data.get("participant_id")
    
    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}
    
    room = f"game:{game_id}"
    
    # Bind participant_id to role for this game
    if participant_id:
        PARTICIPANT_ROLES[(game_id, participant_id)] = role
    
    join_room(room)
    record_event(role, "join", game_id, participant_id=participant_id)
    socketio.emit(
        "system", {"action": "join", "role": role, "game_id": game_id}, to=room
    )

    # Send prior join messages to the newly joined client so they see all roles
    try:
        for joined_role in get_joined_roles(game_id):
            if joined_role == role:
                continue
            socketio.emit(
                "system",
                {"action": "join", "role": joined_role, "game_id": game_id},
                to=request.sid,
            )
    except Exception as e:
        print(f"Failed to replay join roles: {e}")
    print(f"👥 {role} joined room {room}")


@socketio.on("chat")
def handle_chat(data):
    """Chat messages between participants."""
    game_id = data.get("game_id", DEFAULT_GAME_ID)
    role = data.get("role", "unknown")
    participant_id = data.get("participant_id")
    text = data.get("text", "")
    
    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}
    
    # Bind participant_id to role for this game
    if participant_id:
        PARTICIPANT_ROLES[(game_id, participant_id)] = role
    
    record_event(role, "chat", game_id, text=text, participant_id=participant_id)
    socketio.emit(
        "chat", {"role": role, "text": text, "game_id": game_id}, to=f"game:{game_id}"
    )
    print(f"💬 {role}@{game_id}: {text}")


@socketio.on("voice_join")
def handle_voice_join(data):
    """Participant joins the voice mesh for a game."""
    game_id = data.get("game_id", DEFAULT_GAME_ID)
    role = data.get("role", "unknown")
    client_id = data.get("client_id")
    participant_id = data.get("participant_id")

    if not client_id:
        return {"status": "error", "message": "client_id required"}

    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}

    # Bind participant_id to role for this game
    if participant_id:
        PARTICIPANT_ROLES[(game_id, participant_id)] = role

    if game_id not in VOICE_PARTICIPANTS:
        VOICE_PARTICIPANTS[game_id] = {}

    VOICE_PARTICIPANTS[game_id][client_id] = {"role": role, "socket_id": request.sid}
    record_event(role, "voice_join", game_id, participant_id=participant_id)

    # Send the list of existing peers to the new joiner
    peers = [
        {"client_id": cid, "role": info["role"]}
        for cid, info in VOICE_PARTICIPANTS[game_id].items()
        if cid != client_id
    ]
    socketio.emit("peers_list", {"peers": peers}, to=request.sid)
    
    # Notify all OTHER peers that a new peer joined (so they can initiate connection too)
    socketio.emit("new_peer_joined", {"client_id": client_id, "role": role}, to=f"game:{game_id}", skip_sid=request.sid)
    
    print(f"🎙️ {role} (client {client_id}) joined voice in game {game_id}")
    return {"status": "ok"}


@socketio.on("webrtc_signal")
def handle_webrtc_signal(data):
    """Route WebRTC SDP/ICE to specific target peer in the mesh."""
    game_id = data.get("game_id", DEFAULT_GAME_ID)
    from_id = data.get("from_id")
    to_id = data.get("to_id")
    role = data.get("role", "unknown")
    participant_id = data.get("participant_id")
    
    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}
    
    # Bind participant_id to role for this game
    if participant_id:
        PARTICIPANT_ROLES[(game_id, participant_id)] = role

    payload = {
        "game_id": game_id,
        "from_id": from_id,
        "to_id": to_id,
        "role": role,
        "description": data.get("description"),
        "candidate": data.get("candidate"),
    }

    record_event(role, "webrtc_signal", game_id, participant_id=participant_id)

    # Route to specific peer's socket
    if game_id in VOICE_PARTICIPANTS and to_id in VOICE_PARTICIPANTS[game_id]:
        target_socket = VOICE_PARTICIPANTS[game_id][to_id]["socket_id"]
        socketio.emit("webrtc_signal", payload, to=target_socket)
        print(f"Signal from {from_id} to {to_id} in game {game_id}")
    else:
        print(f"Could not route signal: to_id {to_id} not found in game {game_id}")


# ---------------------------------------------------------------------
# API: Transcript
# ---------------------------------------------------------------------
@app.route("/transcript")
def transcript():
    """Return all logged events for a game."""
    game_id = request.args.get("game_id", DEFAULT_GAME_ID)
    limit = int(request.args.get("limit", "200"))
    return jsonify(get_transcript(game_id, limit))


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs("db", exist_ok=True)
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
