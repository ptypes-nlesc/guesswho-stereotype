# guesswho-stereotype 🎲

<img src="static/logo.png" alt="GuessWho Stereotype Research Game Logo" width="200">

This is a web application for playing "Guess Who" game. The goal of the game is to study stereotypes associated with pornography without explicitely asking players about them.

##  ✨ Features (Minimum Viable Product)
- Player 1: Secret card + Yes/No answers  
- Player 2: 12-card grid + question + elimination  
- Moderator: Observes both players + asks clarifications  
- Logging of all turns (questions, answers, eliminations, moderator)

## 🛠️ Tech Stack
- **Frontend:** HTML + JavaScript (Bootstrap for layout)  
- **Backend:** Flask (Python 3.10+)  
- **Storage:** sqlite3
- **Deployment:** Local (MVP), online hosting later
- **Audio:** WebRTC later  

## 🚀 How to Run/Test

### 1. Setup Environment
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start the Application
```bash
# Run Flask application (debug mode on port 5000)
python app.py
```
You should see:
```
* Running on http://127.0.0.1:5000
* Debug mode: on
```

### 3. Open the Three Game Screens
Open these URLs in **separate browser tabs**:

#### 🔹 **Player 1** (Secret Card Holder)
**http://127.0.0.1:5000/player1**
- Shows the randomly chosen secret card
- Click "Yes" or "No" to answer Player 2's questions

#### 🔹 **Player 2** (Guesser) 
**http://127.0.0.1:5000/player2**
- Shows 4x3 grid of 12 cards
- Type yes/no questions and click "Submit"
- Click cards to eliminate them (they get crossed out)

#### 🔹 **Moderator** (Research Observer)
**http://127.0.0.1:5000/moderator**
- Dual-view showing both players via iframes
- Add clarification notes for research purposes
- Monitor entire game flow

### 4. Test Game Flow
1. **Player 2**: Ask a question like "Is this character blonde?"
2. **Player 1**: Click "Yes" or "No" 
3. **Player 2**: Eliminate cards based on the answer
4. **Moderator**: Add research notes as needed


## SQLite database logging

The application persists game transcript to a SQLite database at `db/games.db`. Tables are:
- `games` — game rows (game id, chosen card, created_at)
- `events` — timestamped actions (role, action, text, card, ...)
- `eliminated_cards` — per-game eliminated card entries with timestamps

Quick sqlite3 commands to inspect the database:

Open the DB interactively:
```bash
sqlite3 db/games.db
```
Show tables and schema:
```sql
.tables
.schema events
```
Pretty output examples:
```bash
# Last 50 events
sqlite3 -header -column db/games.db "SELECT * FROM events ORDER BY timestamp DESC LIMIT 50;"

# All chat messages for game 'default'
sqlite3 -header -column db/games.db "SELECT timestamp, role, text FROM events WHERE game_id='default' AND action='chat' ORDER BY timestamp;"

```





