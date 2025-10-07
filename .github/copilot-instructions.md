# Copilot Instructions for GuessWho Stereotype Research Game

## Project Overview

This is a Flask-based web application implementing a multi-player "Guess Who" game for studying stereotypes associated with pornography. The research goal is to observe stereotype patterns without explicitly asking about them.

## Architecture Pattern

- **Three-screen design**: Player 1 (secret card holder), Player 2 (guesser with 12-card grid), Moderator (observer with dual view)
- **In-memory game state**: Single `CHOSEN_CARD` variable holds the secret card for entire session
- **JSON-based logging**: All interactions logged to `data/game_log.json` with timestamps and role identification
- **Stateless HTTP**: No sessions - relies on browser state and shared memory

## Key Components

### Core Flask App (`app.py`)

- Game starts by randomly selecting one card from `data/sample_cards.json`
- Uses `log_turn()` utility for consistent JSON logging format: `{"role": "player1|player2|moderator", "action": "question|answer|eliminate|note", ...}`
- Four main API endpoints mirror the three player actions plus moderator notes

### Frontend Architecture

- **No frameworks**: Plain HTML + vanilla JavaScript in `static/script.js`
- **Role-specific templates**: Each player sees different interface via separate routes (`/player1`, `/player2`, `/moderator`)
- **Moderator dual-view**: Uses iframes to observe both players simultaneously with `pointer-events: none`
- **Visual elimination**: Cards use CSS class `.eliminated` for strikethrough + gray background

### Data Flow Pattern

```
Player 2 asks question → logged → Player 1 answers → logged → Player 2 eliminates cards → logged
                                    ↓
                           Moderator observes + adds clarification notes → logged
```

## Development Conventions

### Card Data Structure

Cards in `data/sample_cards.json` use: `{"id": number, "name": string, "description": string}`

- Currently placeholder data ("Stereotype A", "Stereotype B")
- Grid displays exactly 12 cards in 4x3 CSS grid layout

### API Response Pattern

All endpoints return `{"status": "ok"}` - no error handling implemented yet

### Logging Schema

Every action gets timestamped entry with consistent structure:

- `role`: "player1" | "player2" | "moderator" | "system"
- `action`: "question" | "answer" | "eliminate" | "note" | "card_draw"
- Plus action-specific fields (question, answer, card, note)

## Development Workflow

### Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py  # Runs on debug mode, port 5000
```

### Testing Game Flow

1. Open three browser tabs: `/player1`, `/player2`, `/moderator`
2. Watch `data/game_log.json` for real-time logging
3. Moderator can observe both players via iframe embedding

### Key Directories

- `data/`: Game cards and JSON logs (created automatically)
- `templates/`: Role-specific HTML views
- `static/`: Shared JS/CSS (no card images implemented yet)
- `docs/`: Empty design files (placeholder for future architecture docs)
- `db/`: Empty SQL schema (planned SQLite migration from JSON)

## Project-Specific Patterns

- **Research focus**: This is academic research tool, not entertainment - keep stereotype study purpose in mind
- **MVP constraints**: Currently local-only, JSON storage, no user authentication, single game session
- **Future roadmap**: SQLite migration, online deployment, WebRTC audio, multiple concurrent games
