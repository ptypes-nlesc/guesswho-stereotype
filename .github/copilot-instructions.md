# Copilot Instructions for GuessWho Stereotype Research Game

## Project Overview

This is a Flask-based web application implementing a multi-player "Guess Who" game for studying stereotypes associated with pornography. The research goal is to observe stereotype patterns without explicitly asking about them.

## Architecture Pattern

- **Three-role design**: Player 1 (secret card holder), Player 2 (guesser with 12-card grid), Moderator (session controller and observer)
- **SQLite database**: All game state and events persisted to `db/games.db` with automatic initialization
- **Role-binding system**: participant_id ↔ role mapping stored in DB and in-memory, enforced at route/socket level
- **Token-based authentication**: Moderators generate invitation tokens (30-day expiration) for player access
- **Game state machine**: CLOSED → OPEN → READY → IN_PROGRESS → ENDED → CLOSED state transitions

## Key Components

### Database Schema (`db/games.db`)

**Tables:**
- `games`: game_id (PK), created_at, chosen_card
- `events`: id (PK), game_id, role, action, text, card, participant_id, timestamp
- `eliminated_cards`: (game_id, card_id) -> PK, eliminated_at timestamp
- `participant_bindings`: (game_id, participant_id) -> PK, role, created_at
- `access_tokens`: token (PK), created_at, expires_at (30 days), used_at, participant_id
- `audio_events`: id (PK), game_id, role, start_time, end_time, duration, audio_path, transcript, timestamp

### Core Flask App (`app.py`)

- **Database utilities**: `get_db_conn()`, `init_db()`, `log_event()`, helper getters
- **Game management**: GAME_STATES dict tracks session state per game_id with structure:
  ```python
  {
    'state': 'CLOSED|OPEN|READY|IN_PROGRESS|ENDED',
    'waiting_participants': [{'id': participant_id, 'timestamp': iso_timestamp}, ...],
    'player1_id': uuid_string,
    'player2_id': uuid_string
  }
  ```
- **CURRENT_SESSION_GAME_ID**: Global variable tracking the active game for participant joins
- **PARTICIPANT_ROLES**: In-memory cache mapping (game_id, participant_id) → role
- **Role binding enforcement**: Routes and Socket.IO endpoints validate participant_id matches required role before allowing action
- **Event logging**: All actions logged to `events` table with structured schema (role, action, text, card, timestamp)

### Frontend Architecture

- **No frontend frameworks**: Plain HTML + vanilla JavaScript in `static/script.js`
- **Role-specific templates**: Each player sees different interface via `/player1`, `/player2`, `/moderator` routes
- **Moderator dashboard**: `/dashboard` provides session control (open/close/start/end/reset) and token generation
- **Token-based join flow**: `/join` page accepts URL-encoded token, validates expiry, and routes to `/join/enter` endpoint
- **Visual elimination**: Cards use CSS class `.eliminated` for strikethrough + gray background styling
- **WebRTC voice**: JavaScript WebRTC mesh network in `static/webrtc.js` for real-time peer audio

### Data Flow

```
Moderator logs in
    ↓
Moderator opens entry (state: OPEN, creates new game)
    ↓
Moderator generates tokens (creates access_tokens DB records)
    ↓
Players use tokens to /join (validates token, generates participant_id)
    ↓
Players enter waiting room /join/enter (adds to waiting_participants)
    ↓
When 2 players arrive (state: READY, assigns player1_id, player2_id, binds roles in DB)
    ↓
Moderator starts game (state: IN_PROGRESS, players can now see their views)
    ↓
Player 2 asks question  → Socket.IO chat → Player 1 answers
    ↓
Player 2 eliminates cards → POST /eliminate_card → logged to eliminated_cards table
    ↓
Moderator observes all changes via /moderator view (iframes + live updates)
    ↓
Moderator ends game (state: ENDED)
    ↓
Moderator resets session (state: CLOSED → ready for next game)
```

## Development Conventions

### Card Data Structure

Cards are auto-generated in Python: `CARDS = [{"id": i, "name": f"Card {i}"} for i in range(1, 13)]`

- Direct mapping: Card ID 1 → `static/cards/1.png`, Card ID 2 → `static/cards/2.png`, etc.
- Grid displays exactly 12 cards in 4x3 CSS grid layout
- Visual-only interface with no text descriptions for unbiased research

### API Response Pattern

Most endpoints return `{"status": "ok"}` or error JSON: `{"status": "error", "message": "..."}`

### Game State Transitions

The state machine follows a strict sequence:
1. **CLOSED** → Moderator opens entry
2. **OPEN** → Waiting for 2 participants (can manually close)
3. **READY** → 2 participants joined, awaiting moderator to start (auto-transition when capacity reached)
4. **IN_PROGRESS** → Moderator starts game, players can interact
5. **ENDED** → Moderator ends game
6. **CLOSED** → Moderator resets, returning to initial state

### Logging Schema

Every action logged to `events` table with consistent structure:
- `role`: "player1" | "player2" | "moderator" | "system"
- `action`: "join" | "chat" | "question" | "answer" | "eliminate" | "voice_join" | "webrtc_signal" | "note" | "card_draw" | "session_created" | "game_started" | "game_ended" | "entry_opened" | "entry_closed" | "session_reset" | "tokens_generated"
- Plus action-specific fields: `text`, `card`, `participant_id`, `timestamp`

### Token System

- **Generation**: Moderator calls `/moderator/tokens/generate` with `count` parameter (1-100)
- **Expiration**: 30 days from creation
- **One-time use**: Token becomes invalid after first `/join/enter` use
- **Export**: CSV file with join URLs ready to distribute to participants

## Development Workflow

### Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with required variables
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" > .env
echo "MODERATOR_PASSWORD=your-secure-password" >> .env

# Run the app
python app.py  # Runs on http://localhost:5000
```

### Testing Full Game Flow

1. **Open browser tabs:**
   - Tab 1: `http://localhost:5000/dashboard` (Moderator - log in with MODERATOR_PASSWORD)
   - Tab 2: Inspector → SQLite viewer for `db/games.db`

2. **Moderator workflow:**
   - Click "Open Entry" to create game and enable joins
   - Click "Generate Tokens" to create invites
   - Copy join URLs and test in new browser windows/incognito tabs

3. **Player workflow:**
   - Paste join URL in new browser
   - Accept token → wait for another player
   - Moderator clicks "Start Game" when ready
   - Player 1 sees secret card, Player 2 sees 12-card grid
   - Chat and eliminate cards via UI

4. **Verify database:**
   - Check `games` table has new game_id
   - Check `events` table has all role actions logged
   - Check `eliminated_cards` table tracks card removals
   - Check `access_tokens` table shows used/unused tokens

### Key Directories

- `db/`: SQLite database file `games.db` (auto-created)
- `templates/`: Role-specific HTML views (dashboard, player1, player2, moderator, waiting)
- `static/`: Shared JS/CSS (script.js, style.css, webrtc.js)
- `static/cards/`: Card image files (1.png through 12.png)
- `tests/`: pytest test suite with fixtures for DB and globals

### Running Tests

```bash
pytest tests/ -v
pytest tests/test_auth.py -v  # Authentication tests
pytest tests/test_game_flow.py -v  # Game state transitions
pytest tests/test_gameplay.py -v  # Card elimination, gameplay mechanics
pytest tests/test_role_binding.py -v  # Role enforcement
pytest tests/test_tokens.py -v  # Token generation and validation
```

## Project-Specific Patterns

- **Research focus**: This is an academic research tool, not entertainment - keep stereotype study purpose in mind
- **Privacy**: Participant IDs are UUIDs, tokens are one-time use, no personal data stored
- **Replicability**: All game events logged with full audit trail to enable research analysis
- **Game atomicity**: Once 2 players join waiting room → auto-transition to READY state
- **Session isolation**: Each game session is independent; moderator can run multiple sessions sequentially
- **Real-time updates**: WebSocket (Socket.IO) enables live chat, voice, and elimination broadcast
- **Error recovery**: Token validation prevents rejoin with same token; role binding prevents cross-role access

## Current Implementation Status

**✅ Completed:**
- SQLite database with full schema
- Game state machine (CLOSED/OPEN/READY/IN_PROGRESS/ENDED)
- Token-based player authentication (30-day expiration)
- Role binding system (DB + in-memory)
- Moderator session management (create/open/close/start/end/reset)
- CSV token export for distribution
- Event logging to database
- Socket.IO chat/voice/signaling
- Card elimination tracking
- Full test suite (auth, game flow, gameplay, role binding, tokens)

**🚀 Future Enhancements:**
- Audio recording and transcription integration
- Multi-concurrent session support (not just single `CURRENT_SESSION_GAME_ID`)
- Online deployment (currently local-only)
- Advanced analytics dashboard
- WebRTC audio quality improvements
- Persistent session recovery
