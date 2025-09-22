from flask import Flask, render_template, request, jsonify
import json, os, datetime

app = Flask(__name__)

LOG_FILE = "data/game_log.json"

# ---utility logging
def log_turn(entry):
    """Append a new entry to the JSON log file"""
    if os.path.exists(LOG_FILE):
        with open (LOG_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    entry["timestamp"] = datetime.datetime.now().isoformat()
    data.append(entry)

    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ---routes for game screens
@app.route("/player1")
def player1():
    return render_template("player1.html")

@app.route("/player2")
def player2():
    return render_template("player2.html")

@app.route("/moderator")
def moderator():
    return render_template("moderator.html")

# ---API endpoints
@app.route("/submit_question", methods=["POST"])
def submit_question():
    q = request.json.get("question")
    log_turn({"role": "player2", "action": "question", "question": q})
    return jsonify({"status":"ok"})

@app.route("/submit_answer", method=["POST"])
def submit_answer()
    ans = request.json.get("answer")
    log_turn({"role": "player1", "action": "answer", "answer": ans})

@app.route("/eliminate_card", methods=["POST"])
def eliminate_card():
    cid = request.json.get("card_id")
    log_turn({"role": "player2", "action": "eliminate", "card": cid})
    return jsonify({"status": "ok"})


@app.route("/submit_note", methods=["POST"])
def submit_note():
    note = request.json.get("note")
    log_turn({"role": "moderator", "action": "note", "note": note})
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    app.run(debug=True)

