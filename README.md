# guesswho-stereotype 🎲
This is a web application for playing "Guess Who" game. The goal of the game is to study stereotypes associated with pornography without explicitely asking players about them.

##  ✨ Features (Minimum Viable Product)
- Player 1: Secret card + Yes/No answers  
- Player 2: 12-card grid + question + elimination  
- Moderator: Observes both players + asks clarifications  
- JSON logging of all turns (questions, answers, eliminations, moderator notes)

## 🛠️ Tech Stack
- **Frontend:** HTML + JavaScript (Bootstrap for layout)  
- **Backend:** Flask (Python 3.10+)  
- **Storage:** JSON logs (MVP), upgrade to SQLite later  
- **Deployment:** Local (MVP), online hosting later
- **Audio:** WebRTC later  

## Virtual env

""" 
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
"""
