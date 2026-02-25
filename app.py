import csv
import datetime
import io
import json
import os
import random
import secrets
import pymysql
import time
import uuid
from contextlib import contextmanager
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    make_response,
    render_template,
    request,
    session,
    redirect,
    url_for,
)
from flask_socketio import SocketIO, join_room
import redis

load_dotenv()

# ---------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------
app = Flask(__name__)

# Validate required environment variables
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is required. "
        "Please set it in your .env file or system environment."
    )

app.config.update(
    SECRET_KEY=SECRET_KEY,
    TEMPLATES_AUTO_RELOAD=True,
)
socketio = SocketIO(app, cors_allowed_origins="*")

MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_PORT', 3306)),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASSWORD'),
    'db': int(os.getenv('REDIS_DB', 0)),
    'decode_responses': True,  # Return strings instead of bytes
}

MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD")

# Skip validation during testing
IS_TESTING = os.getenv('TESTING') == '1'

if not IS_TESTING:
    # Validate required environment variables
    if not MODERATOR_PASSWORD:
        raise ValueError(
            "MODERATOR_PASSWORD environment variable is required. "
            "Please set it in your .env file or system environment."
        )

    # Validate MySQL configuration
    if not all([MYSQL_CONFIG['user'], MYSQL_CONFIG['password'], MYSQL_CONFIG['database']]):
        raise ValueError(
            "MySQL configuration incomplete. "
            "Please set MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE in .env"
        )

# Initialize Redis client
try:
    redis_client = redis.Redis(**REDIS_CONFIG)
    redis_client.ping()  # Test connection
    print("✓ Redis connection established")
except Exception as e:
    if not IS_TESTING:
        raise ValueError(f"Redis connection failed: {e}")
    redis_client = None
    print(f"⚠ Redis unavailable: {e}")

@contextmanager
def get_db_conn():
    """Get MySQL connection with context manager."""
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Card catalog (12 cards)
CARDS = [{"id": i, "name": f"Card {i}"} for i in range(1, 13)]

# =====================================================================
# Redis abstraction layer for state management
# =====================================================================

def get_redis():
    """Return Redis client, or fallback to None if unavailable."""
    return redis_client

# GAME_STATES helpers: Redis hash per game
def get_game_state(game_id):
    """Get game state from Redis. Returns dict or None."""
    if not get_redis():
        return GAME_STATES.get(game_id)
    try:
        data = get_redis().hgetall(f"game:{game_id}:state")
        if not data:
            return None
        # Convert JSON fields and "null" sentinels
        if 'waiting_participants' in data:
            data['waiting_participants'] = json.loads(data['waiting_participants'])
        # Convert "null" sentinels back to None
        for key in ['player1_id', 'player2_id']:
            if key in data and data[key] == "null":
                data[key] = None
        return data
    except Exception as e:
        print(f"Error getting game state: {e}")
        return None

def set_game_state(game_id, state_dict):
    """Store game state in Redis."""
    if not get_redis():
        GAME_STATES[game_id] = state_dict
        return
    try:
        # Convert lists/dicts to JSON for storage, handle None values
        data = {}
        for key, value in state_dict.items():
            if value is None:
                data[key] = "null"  # Redis sentinel for None
            elif isinstance(value, (list, dict)):
                data[key] = json.dumps(value)
            else:
                # Keep strings and other scalar types as-is
                data[key] = str(value) if not isinstance(value, str) else value
        get_redis().hset(f"game:{game_id}:state", mapping=data)
    except Exception as e:
        print(f"Error setting game state: {e}")

def delete_game_state(game_id):
    """Delete game state from Redis."""
    if not get_redis():
        GAME_STATES.pop(game_id, None)
        return
    try:
        get_redis().delete(f"game:{game_id}:state")
    except Exception as e:
        print(f"Error deleting game state: {e}")

def get_all_game_states():
    """Get all game states."""
    if not get_redis():
        return GAME_STATES.copy()
    try:
        keys = get_redis().keys("game:*:state")
        result = {}
        for key in keys:
            game_id = key.split(":")[1]
            state = get_game_state(game_id)
            if state:
                result[game_id] = state
        return result
    except Exception as e:
        print(f"Error getting all game states: {e}")
        return GAME_STATES.copy()

# PARTICIPANT_ROLES helpers: Redis hash (game_id:participant_id -> role)
def get_participant_role(game_id, participant_id):
    """Get participant role for a game."""
    if not get_redis():
        return PARTICIPANT_ROLES.get((game_id, participant_id))
    try:
        role = get_redis().hget(f"roles:{game_id}", participant_id)
        return role
    except Exception as e:
        print(f"Error getting participant role: {e}")
        return None

def set_participant_role(game_id, participant_id, role):
    """Store participant role in Redis."""
    if not get_redis():
        PARTICIPANT_ROLES[(game_id, participant_id)] = role
        return
    try:
        get_redis().hset(f"roles:{game_id}", participant_id, role)
    except Exception as e:
        print(f"Error setting participant role: {e}")

def delete_participant_role(game_id, participant_id):
    """Delete participant role from Redis."""
    if not get_redis():
        PARTICIPANT_ROLES.pop((game_id, participant_id), None)
        return
    try:
        get_redis().hdel(f"roles:{game_id}", participant_id)
    except Exception as e:
        print(f"Error deleting participant role: {e}")

def get_all_participant_roles(game_id):
    """Get all participant roles for a game."""
    if not get_redis():
        return {k[1]: v for k, v in PARTICIPANT_ROLES.items() if k[0] == game_id}
    try:
        return get_redis().hgetall(f"roles:{game_id}")
    except Exception as e:
        print(f"Error getting all participant roles: {e}")
        return {}

# VOICE_PARTICIPANTS helpers: Redis hash per game
def get_voice_participants(game_id):
    """Get voice participants for a game."""
    if not get_redis():
        return VOICE_PARTICIPANTS.get(game_id, {})
    try:
        data = get_redis().hgetall(f"voice:{game_id}")
        # Convert JSON strings back to dicts
        result = {}
        for client_id, json_str in data.items():
            result[client_id] = json.loads(json_str)
        return result
    except Exception as e:
        print(f"Error getting voice participants: {e}")
        return {}

def add_voice_participant(game_id, client_id, participant_data):
    """Add a voice participant."""
    if not get_redis():
        if game_id not in VOICE_PARTICIPANTS:
            VOICE_PARTICIPANTS[game_id] = {}
        VOICE_PARTICIPANTS[game_id][client_id] = participant_data
        return
    try:
        get_redis().hset(f"voice:{game_id}", client_id, json.dumps(participant_data))
    except Exception as e:
        print(f"Error adding voice participant: {e}")

def remove_voice_participant(game_id, client_id):
    """Remove a voice participant."""
    if not get_redis():
        if game_id in VOICE_PARTICIPANTS:
            VOICE_PARTICIPANTS[game_id].pop(client_id, None)
        return
    try:
        get_redis().hdel(f"voice:{game_id}", client_id)
    except Exception as e:
        print(f"Error removing voice participant: {e}")

# CURRENT_SESSION_GAME_ID helper
def get_current_session_game_id():
    """Get the current session game ID."""
    if not get_redis():
        return CURRENT_SESSION_GAME_ID
    try:
        game_id = get_redis().get("current_session_game_id")
        return game_id
    except Exception as e:
        print(f"Error getting current session game ID: {e}")
        return CURRENT_SESSION_GAME_ID

def set_current_session_game_id(game_id):
    """Set the current session game ID."""
    if not get_redis():
        global CURRENT_SESSION_GAME_ID
        CURRENT_SESSION_GAME_ID = game_id
        return
    try:
        if game_id is None:
            get_redis().delete("current_session_game_id")
        else:
            get_redis().set("current_session_game_id", game_id)
    except Exception as e:
        print(f"Error setting current session game ID: {e}")

# Track active voice participants per game: {game_id: {client_id: {role, socket_id}}}
VOICE_PARTICIPANTS = {}

# Role binding store: {(game_id, participant_id): role}
PARTICIPANT_ROLES = {}

# Game state management
# Game states: CLOSED -> OPEN -> READY -> IN_PROGRESS -> ENDED -> CLOSED (loop)
GAME_STATES = {
    # game_id: {
    #   'state': 'CLOSED'|'OPEN'|'READY'|'IN_PROGRESS'|'ENDED',
    #   'waiting_participants': [(participant_id, timestamp), ...],
    #   'player1_id': str,
    #   'player2_id': str
    # }
}
CURRENT_SESSION_GAME_ID = None  # The active game session


def init_db():
    """Ensure all tables exist before running the app."""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id VARCHAR(255) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                chosen_card INT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                game_id VARCHAR(255) NOT NULL,
                role VARCHAR(50),
                action VARCHAR(50),
                text LONGTEXT,
                card INT,
                participant_id VARCHAR(255),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
                INDEX idx_game_id (game_id),
                INDEX idx_timestamp (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS eliminated_cards (
                game_id VARCHAR(255) NOT NULL,
                card_id INT NOT NULL,
                eliminated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (game_id, card_id),
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                game_id VARCHAR(255) NOT NULL,
                role VARCHAR(50),
                start_time DATETIME,
                end_time DATETIME,
                duration_seconds FLOAT,
                audio_path TEXT,
                transcript LONGTEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
                INDEX idx_game_id (game_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS participant_bindings (
                game_id VARCHAR(255) NOT NULL,
                participant_id VARCHAR(255) NOT NULL,
                role VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (game_id, participant_id),
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS access_tokens (
                token VARCHAR(255) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                used_at DATETIME,
                participant_id VARCHAR(255),
                INDEX idx_expires_at (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
       

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
            "INSERT INTO events (game_id, role, action, text, card, participant_id, timestamp) VALUES (%s, %s, %s, %s, %s, %s, %s)",
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
                REPLACE INTO eliminated_cards (game_id, card_id, eliminated_at)
                VALUES (%s, %s, %s)
                """,
                (game_id, card, datetime.datetime.now().isoformat()),
            )
        # Context manager auto-commits


def get_eliminated_cards(game_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT card_id FROM eliminated_cards WHERE game_id = %s", (game_id,))
        return {row['card_id'] for row in c.fetchall()}


def get_chosen_card(game_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT chosen_card FROM games WHERE id = %s", (game_id,))
        row = c.fetchone()
        return row['chosen_card'] if row else None


def get_transcript(game_id, limit=200):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM events WHERE game_id = %s ORDER BY id DESC LIMIT %s",
            (game_id, limit),
        )
        return [dict(r) for r in reversed(c.fetchall())]


def get_joined_roles(game_id):
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT DISTINCT role FROM events WHERE game_id = %s AND action = %s",
            (game_id, "join"),
        )
        return {row['role'] for row in c.fetchall()}


# ---------------------------------------------------------------------
# Initialize DB
# ---------------------------------------------------------------------
# Only initialize if not in testing mode
if not os.getenv('TESTING'):
    init_db()


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
            "SELECT role FROM participant_bindings WHERE game_id = %s AND participant_id = %s",
            (game_id, participant_id),
        )
        row = c.fetchone()
        return row['role'] if row else None


def set_participant_binding(game_id, participant_id, role):
    """Store role binding in database."""
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT IGNORE INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (%s, %s, %s, %s)",
            (game_id, participant_id, role, datetime.datetime.now().isoformat()),
        )

# Helper to check role binding (now DB-backed)
def check_role_binding(game_id, participant_id, required_role):
    """
    Enforce role binding: verify participant_id is bound to required_role.
    Source of truth is the database. Creates binding on first route access.
    Returns (allowed: bool, message: str or None)
    """
    if not participant_id:
        return True, None  # No participant_id — allow (backward compat)
    
    # Check DB for existing binding first
    bound_role = get_participant_binding(game_id, participant_id)
    
    if bound_role:
        # Binding exists - allow access if roles match (even if session is closed)
        if bound_role != required_role:
            return False, f"Forbidden: participant is bound to {bound_role}, not {required_role}"
        return True, None
    
    # No binding exists yet - only allow if session is active
    # For non-moderator roles, verify game belongs to current session
    if required_role != "moderator":
        current_game_id = get_current_session_game_id()
        if not current_game_id or game_id != current_game_id:
            return False, "This game session is no longer active"
    else:
        # For moderators, verify game_id matches their session
        moderator_game_id = session.get('moderator_session_game_id')
        if not moderator_game_id or game_id != moderator_game_id:
            return False, "This game session is no longer active"
    
    # First access during active session: create binding in DB
    set_participant_binding(game_id, participant_id, required_role)
    return True, None


@app.route("/dashboard")
def dashboard():
    """Moderator dashboard."""
    if not session.get("moderator"):
        return redirect(url_for("index"))
    # Clear any previous session when moderator goes to dashboard
    session['moderator_session_game_id'] = None
    return render_template("dashboard.html")


@app.route("/player1")
def player1():
    """Player 1 – secret card view."""
    game_id = request.args.get("game_id")
    participant_id = request.args.get("participant_id")
    
    if not game_id:
        return "Missing game_id parameter", 400
    
    # Enforce role binding
    allowed, message = check_role_binding(game_id, participant_id, "player1")
    if not allowed:
        # Still render the page so they see the notification on screen
        chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
        return render_template(
            "player1.html", card={"id": chosen, "name": f"Card {chosen}"}, game_id=game_id
        )
    
    chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
    return render_template(
        "player1.html", card={"id": chosen, "name": f"Card {chosen}"}, game_id=game_id
    )


@app.route("/player2")
def player2():
    """Player 2 – guesser grid view."""
    game_id = request.args.get("game_id")
    participant_id = request.args.get("participant_id")
    
    if not game_id:
        return "Missing game_id parameter", 400
    
    # Enforce role binding
    allowed, message = check_role_binding(game_id, participant_id, "player2")
    if not allowed:
        # Still render the page so they see the notification on screen
        eliminated = get_eliminated_cards(game_id)
        return render_template(
            "player2.html", cards=CARDS, eliminated=eliminated, game_id=game_id
        )
    
    eliminated = get_eliminated_cards(game_id)
    return render_template(
        "player2.html", cards=CARDS, eliminated=eliminated, game_id=game_id
    )


@app.route("/moderator")
def moderator():
    """Moderator live view."""
    game_id = request.args.get("game_id")
    participant_id = request.args.get("participant_id")
    
    if not game_id:
        return "Missing game_id parameter", 400
    
    # Enforce role binding
    allowed, message = check_role_binding(game_id, participant_id, "moderator")
    if not allowed:
        # Still render the page so they see the notification on screen
        chosen = get_chosen_card(game_id) or random.choice(CARDS)["id"]
        eliminated = get_eliminated_cards(game_id)
        return render_template(
            "moderator.html",
            game_id=game_id,
            cards=CARDS,
            eliminated=eliminated,
            secret_card={"id": chosen, "name": f"Card {chosen}"},
        )

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
            "INSERT INTO games (id, created_at, chosen_card) VALUES (%s, %s, %s)",
            (game_id, datetime.datetime.now().isoformat(), chosen_card),
        )
        # Pre-bind participant_ids to roles in DB
        c.execute(
            "INSERT INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (%s, %s, %s, %s)",
            (game_id, player1_id, "player1", datetime.datetime.now().isoformat()),
        )
        c.execute(
            "INSERT INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (%s, %s, %s, %s)",
            (game_id, player2_id, "player2", datetime.datetime.now().isoformat()),
        )
        c.execute(
            "INSERT INTO participant_bindings (game_id, participant_id, role, created_at) VALUES (%s, %s, %s, %s)",
            (game_id, moderator_id, "moderator", datetime.datetime.now().isoformat()),
        )

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
    game_id = data.get("game_id")
    
    if not game_id:
        return jsonify({"status": "error", "message": "game_id required"}), 400
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
# Game Entry Control Routes
# ---------------------------------------------------------------------
@app.route("/game/status")
def game_status():
    """Check game state for active players."""
    game_id = request.args.get("game_id")
    participant_id = request.args.get("participant_id")
    
    if not game_id:
        return jsonify({"status": "error", "message": "game_id required"}), 400
    
    current_game_id = get_current_session_game_id()
    if not current_game_id or not get_game_state(current_game_id):
        return jsonify({
            "state": "CLOSED",
            "is_player": False,
            "message": "This game session is no longer active"
        })
    
    # Only allow access to the current active session game
    if game_id != current_game_id:
        return jsonify({
            "state": "CLOSED",
            "is_player": False,
            "message": "This game session is no longer active"
        })
    
    game_state = get_game_state(current_game_id)
    
    return jsonify({
        "game_id": current_game_id,
        "state": game_state['state'],
        "is_player": participant_id in [game_state.get('player1_id'), game_state.get('player2_id')]
    })


@app.route("/join")
def join_page():
    """Token-based join page for participants."""
    token = request.args.get("token")
    
    if not token:
        return render_template("waiting.html", error="No token provided. You need a valid invitation link to join.")
    
    # Validate token
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT token, expires_at, used_at, participant_id FROM access_tokens WHERE token = %s",
            (token,)
        )
        token_row = c.fetchone()
    
    if not token_row:
        return render_template("waiting.html", error="Invalid token. Please check your invitation link.")
    
    # Check if token is expired
    expires_at = token_row['expires_at']  # MySQL returns datetime object directly
    if datetime.datetime.now() > expires_at:
        return render_template("waiting.html", error="This invitation link has expired.")
    
    # Check if token has been used
    if token_row['used_at']:  # used_at is not NULL
        return render_template("waiting.html", error="This token has already been used and cannot be reused.")
    
    # Token is valid and unused - render waiting page with token
    return render_template("waiting.html", token=token)


@app.route("/join/status")
def join_status():
    """Check if participant can join and get current status."""
    participant_id = request.args.get("participant_id")

    # Check current session status
    current_game_id = get_current_session_game_id()
    if not current_game_id or not get_game_state(current_game_id):
        return jsonify({"status": "closed", "message": "Entry is currently closed"})
    
    game_state = get_game_state(current_game_id)

    # If participant already in the current game, return their role
    if participant_id and game_state.get('state') == 'IN_PROGRESS':
        if game_state.get('player1_id') == participant_id:
            return jsonify({
                "status": "in_game",
                "role": "player1",
                "game_id": current_game_id
            })
        if game_state.get('player2_id') == participant_id:
            return jsonify({
                "status": "in_game",
                "role": "player2",
                "game_id": current_game_id
            })
    
    if game_state['state'] == 'CLOSED':
        return jsonify({"status": "closed", "message": "Entry is currently closed"})
    elif game_state['state'] == 'OPEN':
        waiting_count = len(game_state.get('waiting_participants', []))
        return jsonify({
            "status": "open",
            "message": f"Entry is open. {waiting_count}/2 participants waiting",
            "waiting_count": waiting_count
        })
    elif game_state['state'] == 'READY':
        # Check if this participant is one of the two selected
        if participant_id and participant_id in [game_state.get('player1_id'), game_state.get('player2_id')]:
            return jsonify({
                "status": "ready",
                "message": "Waiting for moderator to start game"
            })
        else:
            return jsonify({
                "status": "closed",
                "message": "Entry is closed (game is ready to start)"
            })
    elif game_state['state'] == 'IN_PROGRESS':
        return jsonify({"status": "closed", "message": "Game in progress"})
    elif game_state['state'] == 'ENDED':
        return jsonify({"status": "closed", "message": "Game has ended"})
    
    return jsonify({"status": "closed", "message": "Unknown state"})


@app.route("/join/enter", methods=["POST"])
def join_enter():
    """Participant attempts to enter the waiting room using a token."""
    data = request.get_json() or {}
    token = data.get("token")
    
    if not token:
        return jsonify({"status": "error", "message": "No token provided"}), 400
    
    # Validate token
    with get_db_conn() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT token, expires_at, used_at, participant_id FROM access_tokens WHERE token = %s",
            (token,)
        )
        token_row = c.fetchone()
    
    if not token_row:
        return jsonify({"status": "error", "message": "Invalid token"}), 400
    
    # Check if token is expired
    expires_at = token_row['expires_at']  # MySQL returns datetime object directly
    if datetime.datetime.now() > expires_at:
        return jsonify({"status": "error", "message": "Token has expired"}), 400
    
    # Check if token has been used
    if token_row['used_at']:  # used_at is not NULL
        # Token already used - reject with error
        return jsonify({"status": "error", "message": "This token has already been used and cannot be reused"}), 400
    else:
        # Token not yet used - generate participant_id and mark token as used
        participant_id = str(uuid.uuid4())
        
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE access_tokens SET used_at = %s, participant_id = %s WHERE token = %s",
                (datetime.datetime.now().isoformat(), participant_id, token)
            )
            # Context manager auto-commits
    
    current_game_id = get_current_session_game_id()
    if not current_game_id or not get_game_state(current_game_id):
        return jsonify({"status": "error", "message": "No active session"}), 400
    
    game_state = get_game_state(current_game_id)
    
    if game_state['state'] != 'OPEN':
        return jsonify({"status": "error", "message": "Entry is not open"}), 400
    
    # Add to waiting list if not already there
    if 'waiting_participants' not in game_state:
        game_state['waiting_participants'] = []
    
    # Check if participant is already in waiting list
    if any(p['id'] == participant_id for p in game_state['waiting_participants']):
        return jsonify({
            "status": "ok",
            "participant_id": participant_id,
            "waiting_count": len(game_state['waiting_participants'])
        })
    
    if len(game_state['waiting_participants']) >= 2:
        return jsonify({"status": "error", "message": "Capacity reached"}), 400
    
    game_state['waiting_participants'].append({
        'id': participant_id,
        'timestamp': datetime.datetime.now().isoformat()
    })
    
    print(f"Participant {participant_id} entered waiting room. Count: {len(game_state['waiting_participants'])}/2")
    
    # Auto-close if capacity reached
    if len(game_state['waiting_participants']) == 2:
        game_state['state'] = 'READY'
        # Assign roles
        game_state['player1_id'] = game_state['waiting_participants'][0]['id']
        game_state['player2_id'] = game_state['waiting_participants'][1]['id']
        
        # Save updated state to Redis
        set_game_state(current_game_id, game_state)
        
        # Bind roles in database
        set_participant_binding(current_game_id, game_state['player1_id'], 'player1')
        set_participant_binding(current_game_id, game_state['player2_id'], 'player2')
        
        record_event("system", "entry_closed", current_game_id, text="Capacity reached (2/2)")
        print(f"Game {current_game_id} ready with 2 participants")
    else:
        # Save updated state to Redis
        set_game_state(current_game_id, game_state)
    
    return jsonify({
        "status": "ok",
        "participant_id": participant_id,
        "waiting_count": len(game_state['waiting_participants']),
        "game_id": current_game_id,
    })


@app.route("/moderator/control")
def moderator_control():
    """Moderator control panel."""
    if not session.get("moderator"):
        return redirect(url_for("index"))
    return redirect(url_for("dashboard"))


@app.route("/moderator/control/status")
def moderator_control_status():
    """Get current game state for moderator."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    # Use moderator's session to track their current game, fall back to global
    moderator_game_id = session.get('moderator_session_game_id')
    
    # If moderator doesn't have a game_id in session, check the global
    if not moderator_game_id:
        moderator_game_id = get_current_session_game_id()
    
    if not moderator_game_id or not get_game_state(moderator_game_id):
        return jsonify({
            "status": "no_session",
            "message": "No active session"
        })
    
    game_state = get_game_state(moderator_game_id)
    
    # If session is CLOSED, clear it so moderator starts fresh
    if game_state['state'] == 'CLOSED':
        session['moderator_session_game_id'] = None
        return jsonify({
            "status": "no_session",
            "message": "No active session"
        })
    
    return jsonify({
        "status": "ok",
        "game_id": moderator_game_id,
        "state": game_state['state'],
        "waiting_count": len(game_state.get('waiting_participants', [])),
        "player1_id": game_state.get('player1_id'),
        "player2_id": game_state.get('player2_id')
    })


@app.route("/moderator/control/open", methods=["POST"])
def moderator_open_entry():
    """Moderator opens entry for participants."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    moderator_game_id = session.get('moderator_session_game_id')
    game_state = get_game_state(moderator_game_id) if moderator_game_id else None
    
    # Auto-reset and reopen ended/closed sessions; create new if none exists or in progress
    if moderator_game_id and game_state and game_state.get('state') in ['ENDED', 'CLOSED']:
        game_state['state'] = 'OPEN'
        game_state['waiting_participants'] = []
        game_state['player1_id'] = None
        game_state['player2_id'] = None
        set_game_state(moderator_game_id, game_state)
        set_current_session_game_id(moderator_game_id)
        record_event("system", "session_reset", moderator_game_id, text="Auto-reset on open entry")
        record_event("system", "entry_opened", moderator_game_id, text="Entry opened after auto-reset")
        print(f"🔄 Auto-reset and opened entry for session {moderator_game_id}")
    elif not moderator_game_id or not game_state or game_state.get('state') in ['IN_PROGRESS']:
        # Create new game
        game_id = uuid.uuid4().hex
        chosen_card = random.choice(CARDS)["id"]
        
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO games (id, created_at, chosen_card) VALUES (%s, %s, %s)",
                (game_id, datetime.datetime.now().isoformat(), chosen_card),
            )
        # Context manager auto-commits on successful exit
        
        moderator_game_id = game_id
        session['moderator_session_game_id'] = game_id
        set_game_state(game_id, {
            'state': 'OPEN',
            'waiting_participants': [],
            'player1_id': None,
            'player2_id': None
        })
        
        # Update the global for participant joins
        set_current_session_game_id(game_id)
        
        record_event("system", "session_created", game_id, text=f"New session created, entry opened")
        print(f"✅ Created new session {game_id} and opened entry")
    else:
        # Open existing session when already open/ready
        set_current_session_game_id(moderator_game_id)
    
    return jsonify({"status": "ok", "game_id": moderator_game_id})


@app.route("/moderator/control/close", methods=["POST"])
def moderator_close_entry():
    """Moderator closes entry for participants."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    moderator_game_id = session.get('moderator_session_game_id')
    if not moderator_game_id:
        moderator_game_id = get_current_session_game_id()
        if moderator_game_id:
            session['moderator_session_game_id'] = moderator_game_id
    if not moderator_game_id or not get_game_state(moderator_game_id):
        return jsonify({"status": "error", "message": "No active session"}), 400
    
    game_state = get_game_state(moderator_game_id)
    game_state['state'] = 'CLOSED'
    set_game_state(moderator_game_id, game_state)
    
    record_event("system", "entry_closed", moderator_game_id, text="Manually closed by moderator")
    print(f"🔒 Closed entry for session {moderator_game_id}")
    
    return jsonify({"status": "ok"})


@app.route("/moderator/control/start", methods=["POST"])
def moderator_start_game():
    """Moderator starts the game (transitions READY -> IN_PROGRESS)."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    moderator_game_id = session.get('moderator_session_game_id')
    if not moderator_game_id:
        moderator_game_id = get_current_session_game_id()
        if moderator_game_id:
            session['moderator_session_game_id'] = moderator_game_id
    if not moderator_game_id or not get_game_state(moderator_game_id):
        return jsonify({"status": "error", "message": "No active session"}), 400
    
    game_state = get_game_state(moderator_game_id)
    
    if game_state['state'] != 'READY':
        return jsonify({"status": "error", "message": f"Cannot start game in state: {game_state['state']}"}), 400
    
    if not game_state.get('player1_id') or not game_state.get('player2_id'):
        return jsonify({"status": "error", "message": "Missing player IDs"}), 400
    
    game_state['state'] = 'IN_PROGRESS'
    set_game_state(moderator_game_id, game_state)
    
    # Update global for participant joins
    set_current_session_game_id(moderator_game_id)
    
    record_event("system", "game_started", moderator_game_id, 
                 text=f"Game started with P1={game_state['player1_id'][:8]}... P2={game_state['player2_id'][:8]}...")
    print(f"🎮 Started game {moderator_game_id}")
    
    return jsonify({
        "status": "ok",
        "game_id": moderator_game_id,
        "player1_url": f"/player1?game_id={moderator_game_id}&participant_id={game_state['player1_id']}",
        "player2_url": f"/player2?game_id={moderator_game_id}&participant_id={game_state['player2_id']}",
        "moderator_url": f"/moderator?game_id={moderator_game_id}"
    })


@app.route("/moderator/control/end", methods=["POST"])
def moderator_end_game():
    """Moderator ends the game (transitions IN_PROGRESS -> ENDED)."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    moderator_game_id = session.get('moderator_session_game_id')
    if not moderator_game_id:
        moderator_game_id = get_current_session_game_id()
        if moderator_game_id:
            session['moderator_session_game_id'] = moderator_game_id
    if not moderator_game_id or not get_game_state(moderator_game_id):
        return jsonify({"status": "error", "message": "No active session"}), 400
    
    game_state = get_game_state(moderator_game_id)
    if game_state.get('state') == 'CLOSED':
        return jsonify({"status": "error", "message": "No active session"}), 400
    game_state['state'] = 'ENDED'
    set_game_state(moderator_game_id, game_state)
    
    record_event("system", "game_ended", moderator_game_id)
    print(f"🏁 Ended game {moderator_game_id}")
    
    return jsonify({"status": "ok"})


@app.route("/moderator/control/reset", methods=["POST"])
def moderator_reset_session():
    """Moderator resets session (transitions ENDED -> CLOSED)."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    moderator_game_id = session.get('moderator_session_game_id')
    if not moderator_game_id:
        moderator_game_id = get_current_session_game_id()
        if moderator_game_id:
            session['moderator_session_game_id'] = moderator_game_id
    if not moderator_game_id or not get_game_state(moderator_game_id):
        return jsonify({"status": "error", "message": "No active session"}), 400
    
    game_state = get_game_state(moderator_game_id)
    game_state['state'] = 'CLOSED'
    game_state['waiting_participants'] = []
    game_state['player1_id'] = None
    game_state['player2_id'] = None
    set_game_state(moderator_game_id, game_state)
    
    # Clear the global session tracker so participants see "entry closed"
    set_current_session_game_id(None)
    session['moderator_session_game_id'] = None
    
    record_event("system", "session_reset", moderator_game_id)
    print(f"🔄 Reset session {moderator_game_id}")
    
    return jsonify({"status": "ok"})


@app.route("/moderator/tokens/generate", methods=["POST"])
def moderator_generate_tokens():
    """Generate access tokens for participant invitations."""
    if not session.get("moderator"):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    data = request.get_json() or {}
    count = data.get("count", 1)
    
    # Validate count
    if not isinstance(count, int) or count < 1 or count > 100:
        return jsonify({"status": "error", "message": "Count must be between 1 and 100"}), 400
    
    # Generate tokens (30 day expiration)
    tokens = []
    created_at = datetime.datetime.now().isoformat()
    expires_at = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
    
    with get_db_conn() as conn:
        c = conn.cursor()
        for _ in range(count):
            token = secrets.token_urlsafe(32)
            c.execute(
                "INSERT INTO access_tokens (token, created_at, expires_at, used_at, participant_id) VALUES (%s, %s, %s, NULL, NULL)",
                (token, created_at, expires_at)
            )
            tokens.append(token)
        # Context manager auto-commits
    
    # Generate CSV content
    output = io.StringIO()
    csv_writer = csv.writer(output)
    csv_writer.writerow(['join_url'])
    
    # Use request.host_url to get the base URL
    base_url = request.host_url.rstrip('/')
    for token in tokens:
        join_url = f"{base_url}/join?token={token}"
        csv_writer.writerow([join_url])
    
    # Create CSV response
    csv_content = output.getvalue()
    response = make_response(csv_content)
    response.headers['Content-Type'] = 'text/csv'
    # Use local time with proper timezone offset
    local_time = datetime.datetime.fromtimestamp(time.time())
    response.headers['Content-Disposition'] = f'attachment; filename=access_tokens_{local_time.strftime("%Y%m%d_%H%M%S")}.csv'
    
    record_event("moderator", "tokens_generated", "system", text=f"Generated {count} tokens")
    
    return response


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
    
    bound_role = get_participant_role(game_id, participant_id)
    if bound_role and bound_role != claimed_role:
        return False, f"Role mismatch: participant bound to {bound_role}, not {claimed_role}"
    
    return True, None


# ---------------------------------------------------------------------
@socketio.on("join")
def handle_join(data):
    """Clients join a shared room by game ID."""
    game_id = data.get("game_id")
    role = data.get("role", "unknown")
    participant_id = data.get("participant_id")
    
    if not game_id:
        return {"status": "error", "message": "game_id required"}
    
    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}
    
    room = f"game:{game_id}"
    
    # Bind participant_id to role for this game
    if participant_id:
        set_participant_role(game_id, participant_id, role)
    
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
    game_id = data.get("game_id")
    role = data.get("role", "unknown")
    participant_id = data.get("participant_id")
    text = data.get("text", "")
    
    if not game_id:
        return {"status": "error", "message": "game_id required"}
    
    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}
    
    # Bind participant_id to role for this game
    if participant_id:
        set_participant_role(game_id, participant_id, role)
    
    record_event(role, "chat", game_id, text=text, participant_id=participant_id)
    socketio.emit(
        "chat", {"role": role, "text": text, "game_id": game_id}, to=f"game:{game_id}"
    )
    print(f"💬 {role}@{game_id}: {text}")


@socketio.on("voice_join")
def handle_voice_join(data):
    """Participant joins the voice mesh for a game."""
    game_id = data.get("game_id")
    role = data.get("role", "unknown")
    client_id = data.get("client_id")
    participant_id = data.get("participant_id")
    
    if not game_id:
        return {"status": "error", "message": "game_id required"}
    if not client_id:
        return {"status": "error", "message": "client_id required"}

    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}

    # Bind participant_id to role for this game
    if participant_id:
        set_participant_role(game_id, participant_id, role)

    add_voice_participant(game_id, client_id, {"role": role, "socket_id": request.sid})
    record_event(role, "voice_join", game_id, participant_id=participant_id)

    # Send the list of existing peers to the new joiner
    voice_participants = get_voice_participants(game_id)
    peers = [
        {"client_id": cid, "role": info["role"]}
        for cid, info in voice_participants.items()
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
    game_id = data.get("game_id")
    from_id = data.get("from_id")
    to_id = data.get("to_id")
    role = data.get("role", "unknown")
    participant_id = data.get("participant_id")
    
    if not game_id:
        return {"status": "error", "message": "game_id required"}
    
    # Validate role binding
    valid, error = validate_role_binding(game_id, participant_id, role)
    if not valid:
        return {"status": "error", "message": error}
    
    # Bind participant_id to role for this game
    if participant_id:
        set_participant_role(game_id, participant_id, role)

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
    voice_participants = get_voice_participants(game_id)
    if to_id in voice_participants:
        target_socket = voice_participants[to_id]["socket_id"]
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
    game_id = request.args.get("game_id")
    
    if not game_id:
        return jsonify({"status": "error", "message": "game_id required"}), 400
    
    limit = int(request.args.get("limit", "200"))
    return jsonify(get_transcript(game_id, limit))


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs("db", exist_ok=True)
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
