# Copilot Instructions for GuessWho Stereotype Research Game

## Project Overview

This is a Flask-based web application implementing a multi-player "Guess Who" game for studying stereotypes associated with pornography. The research goal is to observe stereotype patterns without explicitly asking about them.

## Architecture Pattern

- **Three-role design**: Player 1 (secret card holder), Player 2 (guesser with 12-card grid), Moderator (session controller and observer)
- **MySQL database**: Persistent game/session/chat/audit data in MySQL
- **Redis-backed runtime state**: Active session state, role cache, and voice participants (with in-memory fallback)
- **Role-binding system**: participant_id ↔ role mapping stored in DB and in-memory, enforced at route/socket level
- **Token-based authentication**: Moderators generate invitation tokens (30-day expiration) for player access
- **Game state machine**: CLOSED → OPEN → READY → IN_PROGRESS → ENDED → CLOSED state transitions

## Key Components

### Database Schema (MySQL)

**Tables:**
- `cards`: id, name, image_path, created_at
- `participants`: id, created_at
- `games`: id, created_at
- `rounds`: (game_id, round_number) PK, chosen_card_id, started_at, ended_at
- `participant_bindings`: (game_id, participant_id, round_number) PK, role, bound_at
- `events`: id PK, game_id, participant_id, action, text, timestamp (**system events only**)
- `chat`: id PK, game_id, participant_id, role, text, timestamp
- `eliminated_cards`: (game_id, round_number, card_id) PK, eliminated_at
- `audio_events`: id PK, game_id, participant_id, start_time, end_time, audio_path, transcript, timestamp
- `access_tokens`: token PK, created_at, expires_at (30 days), used_at, participant_id

### Core Flask App (`app.py`)

- **Database utilities**: `get_db_conn()`, `init_db()`, `log_event()`, helper getters
- **Game management**: Redis-backed state with in-memory fallback. Per-game state structure:
  ```python
  {
    'state': 'CLOSED|OPEN|READY|IN_PROGRESS|ENDED',
    'waiting_participants': [{'id': participant_id, 'timestamp': iso_timestamp}, ...],
        'player1_id': uuid_string,
        'player2_id': uuid_string,
        'round_number': int,
        'round_phase': 'ACTIVE|COMPLETE'
  }
  ```
- **CURRENT_SESSION_GAME_ID**: Global variable tracking the active game for participant joins
- **PARTICIPANT_ROLES**: In-memory cache mapping (game_id, participant_id) → role
- **Role binding enforcement**: Routes and Socket.IO endpoints validate participant_id matches required role before allowing action
- **Logging split**:
    - `events` = system/session events only
    - `chat` = chat messages
    - `eliminated_cards` = elimination facts

### Moderator Identity

- Moderator authentication is session/password based (`session["moderator"]`).
- Moderator is **not** modeled as a participant ID in normal flow.
- Player participant IDs are the authoritative identities for binding and gameplay.

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

`events` table stores only system/session events, e.g.:
- `session_created`, `entry_closed`, `game_started`, `game_ended`, `session_reset`, `tokens_generated`, `roles_swapped`, `join`, `voice_join`, `webrtc_signal`

`chat` table stores participant/moderator chat rows:
- `game_id`, `participant_id` (nullable for moderator), `role`, `text`, `timestamp`

`eliminated_cards` stores elimination facts:
- `game_id`, `round_number`, `card_id`, `eliminated_at`

Notes:
- `card_draw` is not stored in `events` (secret card is in `rounds.chosen_card_id`).
- `events` no longer has a `card_id` column.

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
echo "MYSQL_HOST=localhost" >> .env
echo "MYSQL_PORT=3306" >> .env
echo "MYSQL_USER=your_user" >> .env
echo "MYSQL_PASSWORD=your_password" >> .env
echo "MYSQL_DATABASE=your_database" >> .env
echo "REDIS_HOST=localhost" >> .env
echo "REDIS_PORT=6379" >> .env
echo "REDIS_DB=0" >> .env

# Run the app
python app.py  # Runs on http://localhost:5000
```

### Testing Full Game Flow

1. **Open browser tabs:**
   - Tab 1: `http://localhost:5000/dashboard` (Moderator - log in with MODERATOR_PASSWORD)
    - Tab 2: MySQL client/query tool

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
    - Check `events` table has system/session actions
    - Check `chat` table has chat rows
   - Check `eliminated_cards` table tracks card removals
   - Check `access_tokens` table shows used/unused tokens

### Key Directories

- `db/`: local artifacts (legacy SQLite file may exist but is not source of truth)
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
- MySQL schema initialization (cards, participants, games, rounds, bindings, events, chat, eliminations, tokens, audio)
- Redis-backed runtime state with in-memory fallback
- Game state machine (CLOSED/OPEN/READY/IN_PROGRESS/ENDED)
- Token-based player authentication (30-day expiration)
- Role binding system (DB + in-memory)
- Moderator session management (create/open/close/start/end/reset)
- CSV token export for distribution
- Split logging model (events/chat/eliminations)
- Socket.IO chat/voice/signaling
- Card elimination tracking per round
- Round lifecycle timestamps (`started_at`, `ended_at`)
- Full test suite (auth, game flow, gameplay, role binding, tokens)

**🚀 Future Enhancements:**
- Audio recording and transcription integration
- Multi-concurrent session support (not just single `CURRENT_SESSION_GAME_ID`)
- Online deployment (currently local-only)
- Advanced analytics dashboard
- WebRTC audio quality improvements
- Persistent session recovery
