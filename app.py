import datetime
import json
import os
import random

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

LOG_FILE = "data/game_log.json"


# ---utility logging
def log_turn(entry):
    """Append a new entry to the JSON log file, handling empty file safely."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
        try:
            with open(LOG_FILE, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = []  # reset if file is invalid
    else:
        data = []

    entry["timestamp"] = datetime.datetime.now().isoformat()
    data.append(entry)

    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---cards-setup (auto-generate from 1-12)
CARDS = [{"id": i, "name": f"Card {i}"} for i in range(1, 13)]

# ---store the chosen card in memory per game session
CHOSEN_CARD = random.choice(CARDS)
log_turn({"role": "system", "action": "card_draw", "card": CHOSEN_CARD})

# ---track eliminated cards
ELIMINATED_CARDS = set()
LAST_UPDATE = 0


# ---routes for game screens
@app.route("/player1")
def player1():
    return render_template("player1.html", card=CHOSEN_CARD)


@app.route("/player2")
def player2():
    print(f"DEBUG: ELIMINATED_CARDS = {ELIMINATED_CARDS}")  # Debug output
    return render_template("player2.html", cards=CARDS, eliminated=ELIMINATED_CARDS)


@app.route("/moderator")
def moderator():
    return render_template("moderator.html")


# ---API endpoints
@app.route("/submit_question", methods=["POST"])
def submit_question():
    q = request.json.get("question")
    payload = {"role": "player2", "action": "question", "question": q}
    log_turn(payload)
    # broadcast to all connected clients
    socketio.emit('question', payload, broadcast=True)
    return jsonify({"status": "ok"})


# --- Socket event handlers
@socketio.on('join')
def handle_join(data):
    """Client asks to join a game room. data should contain game_id."""
    game_id = data.get('game_id', 'default')
    room = f"game:{game_id}"
    join_room(room)
    # Optionally notify room that someone joined
    socketio.emit('system', {'action': 'join', 'room': room}, room=room)


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
    # broadcast to room
    socketio.emit('chat', payload, room=room)


@app.route('/submit_chat', methods=['POST'])
def submit_chat():
    """HTTP fallback for submitting chat (also logs and emits to room)."""
    data = request.json or {}
    game_id = data.get('game_id', 'default')
    room = f"game:{game_id}"
    payload = {
        'role': data.get('role', 'unknown'),
        'action': 'chat',
        'text': data.get('text', ''),
        'game_id': game_id,
    }
    log_turn(payload)
    socketio.emit('chat', payload, room=room)
    return jsonify({'status': 'ok'})


@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    ans = request.json.get("answer")
    payload = {"role": "player1", "action": "answer", "answer": ans}
    log_turn(payload)
    socketio.emit('answer', payload, broadcast=True)
    return jsonify({"status": "ok"})


@app.route("/eliminate_card", methods=["POST"])
def eliminate_card():
    global LAST_UPDATE
    cid = request.json.get("card_id")
    ELIMINATED_CARDS.add(int(cid))  # Add to server-side tracking
    LAST_UPDATE = datetime.datetime.now().timestamp()  # Update timestamp
    print(f"DEBUG: Eliminated card {cid}, ELIMINATED_CARDS now = {ELIMINATED_CARDS}")  # Debug
    payload = {"role": "player2", "action": "eliminate", "card": cid}
    log_turn(payload)
    # let all clients know which card was eliminated
    socketio.emit('eliminate', {"card": int(cid), "eliminated": list(ELIMINATED_CARDS), **payload}, broadcast=True)
    return jsonify({"status": "ok"})


@app.route("/submit_note", methods=["POST"])
def submit_note():
    note = request.json.get("note")
    payload = {"role": "moderator", "action": "note", "note": note}
    log_turn(payload)
    socketio.emit('note', payload, broadcast=True)
    return jsonify({"status": "ok"})


@app.route("/game_status")
def game_status():
    """Return current game status for moderator polling"""
    return jsonify({
        "eliminated_count": len(ELIMINATED_CARDS),
        "last_update": LAST_UPDATE
    })


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    # Use Socket.IO runner so websocket clients work in development
    socketio.run(app, debug=True)
