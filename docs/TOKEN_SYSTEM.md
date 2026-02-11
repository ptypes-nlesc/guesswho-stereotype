# Token-Based Invitation System

## Overview

The GuessWho Stereotype game now implements a secure, single-use invitation token system for participant access. This replaces the previous open entry system and provides better control over participant management.

## Key Features

### 1. **Single-Use Invitation Tokens**
- Moderator generates unique, unguessable tokens for each participant
- Each token can only be redeemed once
- Tokens are bound to specific games but not to personal identity
- Format: `https://<host>/join?token=<uuid>`

### 2. **Persistent Participant Identifiers**
- Upon token redemption, a unique participant ID is created
- Participant ID persists throughout the session (stored in session cookie)
- Allows participants to complete both roles within the same game session

### 3. **Role Assignment Flow**
- Participant redeems token → enters waiting room
- Moderator assigns role (player1/player2) dynamically
- Real-time notification via SocketIO when role is assigned
- Automatic redirect to appropriate game view

### 4. **Role Switching**
- Moderator can switch participant roles mid-session
- Useful for allowing participants to experience both perspectives
- Immediate notification and redirect upon role switch

## Database Schema

### invitation_tokens
```sql
CREATE TABLE invitation_tokens (
    token TEXT PRIMARY KEY,
    game_id TEXT,
    created_at TEXT,
    used_at TEXT,           -- NULL until redeemed
    participant_id TEXT,    -- Set when redeemed
    UNIQUE(token)
)
```

### participants
```sql
CREATE TABLE participants (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    last_seen TEXT
)
```

### participant_bindings (existing, enhanced)
```sql
CREATE TABLE participant_bindings (
    game_id TEXT,
    participant_id TEXT,
    role TEXT,
    created_at TEXT,
    PRIMARY KEY (game_id, participant_id)
)
```

## API Endpoints

### Moderator Endpoints

#### `POST /api/generate_token`
Generate a new invitation token.

**Request:**
```json
{
    "game_id": "abc123...",
    "email": "participant@example.com"  // optional, for reference only
}
```

**Response:**
```json
{
    "status": "ok",
    "token": "def456...",
    "join_url": "https://host/join?token=def456..."
}
```

#### `POST /api/assign_role`
Assign a role to a waiting participant.

**Request:**
```json
{
    "participant_id": "p123...",
    "role": "player1",  // or "player2"
    "game_id": "abc123..."
}
```

#### `POST /api/switch_role`
Switch a participant's role mid-session.

**Request:**
```json
{
    "participant_id": "p123...",
    "new_role": "player2",
    "game_id": "abc123..."
}
```

#### `GET /api/waiting_participants?game_id=<id>`
Get list of participants in waiting room.

**Response:**
```json
{
    "status": "ok",
    "waiting_participants": [
        {
            "id": "p123...",
            "created_at": "2026-02-09T...",
            "last_seen": "2026-02-09T...",
            "used_at": "2026-02-09T..."
        }
    ],
    "assigned_count": 0
}
```

#### `GET /api/assigned_participants?game_id=<id>`
Get list of participants with assigned roles.

### Participant Endpoints

#### `GET /join?token=<token>`
Redeem invitation token and enter waiting room.

- Validates token exists and is unused
- Creates persistent participant ID
- Marks token as used
- Stores participant_id in session
- Redirects to `/waiting?participant_id=<id>`

#### `GET /waiting?participant_id=<id>`
Waiting room for participants.

- Displays waiting status
- Listens for role assignment via SocketIO
- Auto-redirects to game view when role is assigned

## SocketIO Events

### `join_participant_room`
Join a participant-specific room for notifications.

**Client → Server:**
```json
{
    "participant_id": "p123..."
}
```

### `role_assigned`
Notification when moderator assigns a role.

**Server → Client:**
```json
{
    "role": "player1",
    "game_id": "abc123..."
}
```

### `role_switched`
Notification when moderator switches participant's role.

**Server → Client:**
```json
{
    "new_role": "player2",
    "game_id": "abc123..."
}
```

## Usage Flow

### Research Session Setup

1. **Moderator logs in** (`/login`)
2. **Access control panel** (`/dashboard` → "Open Control Panel")
3. **Generate invitation tokens**:
   - Enter participant email (optional, for reference)
   - Click "Generate Token"
   - Copy invitation URL
   - Send via email or other channel
4. **Monitor waiting room**:
   - See participants as they redeem tokens
   - Waiting participants appear in "⏳ Waiting Participants" section
5. **Assign roles**:
   - Click "🎭 Player 1" or "🔍 Player 2" for each participant
   - Participants are automatically redirected to their role view
6. **Monitor game**:
   - Use moderator observer view to watch gameplay
   - Switch roles mid-session if needed
7. **End session**:
   - Game data is logged to database
   - Generate new tokens for next pair of participants

### Participant Experience

1. **Receive invitation email** with join URL
2. **Click link** → Token validation
3. **Enter waiting room** → "Waiting for role assignment..."
4. **Role assigned** → Automatic redirect to game view
5. **Play game** in assigned role
6. **Role switched** (optional) → Automatic redirect to new role view

## Security Features

- **Unguessable tokens**: UUIDv4 tokens (128-bit randomness)
- **Single-use**: Token marked as used after first redemption
- **No personal binding**: Tokens not tied to email/identity
- **Session persistence**: participant_id stored in secure session cookie
- **Moderator authentication**: All token operations require moderator login

## Email as Delivery Channel

Email is used **solely as a delivery channel** for invitation links. The system:
- Does NOT verify email addresses
- Does NOT store email as identity
- Does NOT require email to join (direct link access works)
- Optionally logs email for moderator reference only

This approach ensures participant anonymity while providing a convenient distribution mechanism.

## Migration Notes

This system coexists with the existing "Quick Game Mode" which generates pre-assigned participant URLs. The two modes are:

1. **Token-Based Mode** (New): Moderator control panel with dynamic role assignment
2. **Quick Game Mode** (Legacy): Instant game creation with pre-generated URLs

Both modes use the same database schema and game logic.
