# API Reference

This page summarizes HTTP routes and Socket.IO events exposed by the application.

## Base assumptions

- JSON responses follow a simple shape:
  - success: {"status": "ok", ...}
  - error: {"status": "error", "message": "..."}
- Participant routes usually depend on game_id and participant_id.
- Moderator routes require moderator session authentication.

## HTTP Routes

### Public / Session

- GET /
  - Moderator login page.

- POST /login
  - Authenticates moderator using MODERATOR_PASSWORD.

- GET /logout
  - Clears moderator session.

- GET /game/status
  - Query: game_id, optional participant_id.
  - Returns active state and whether participant is assigned.

### Participant Access

- GET /join
  - Query: token.
  - Validates token and returns waiting page context.

- GET /join/status
  - Query: optional participant_id.
  - Returns entry availability based on active session state.

- POST /join/enter
  - Body: {"token": "..."}
  - Redeems token, creates participant, enters waiting list.

### Player Views

- GET /player1
  - Query: game_id, participant_id.
  - Secret-card holder view.

- GET /player2
  - Query: game_id, participant_id.
  - Guesser grid view.

- POST /eliminate_card
  - Body: {"game_id": "...", "card_id": n}
  - Eliminates a card for current round and broadcasts updates.

### Moderator Views and Controls

- GET /dashboard
  - Moderator dashboard.

- GET /moderator
  - Query: game_id.
  - Live observer panel.

- GET /moderator/control
  - Redirects to dashboard.

- GET /moderator/control/status
  - Returns current moderator game state and control flags.

- POST /moderator/control/open
  - Opens entry and creates a session if needed.

- POST /moderator/control/close
  - Closes participant entry.

- POST /moderator/control/start
  - Transitions READY -> IN_PROGRESS.

- POST /moderator/control/end
  - Transitions IN_PROGRESS -> ENDED.

- POST /moderator/control/swap_roles
  - Swaps player roles and starts round 2.

- POST /moderator/control/reset
  - Resets current session to CLOSED.

- POST /moderator/control/recording/start
  - Starts a recording session while game state is IN_PROGRESS.
  - Broadcasts recording_start to room game:{game_id}.
  - Response includes recording_id and server_ts (UTC ISO-8601).

- POST /moderator/control/recording/stop
  - Stops the active recording session.
  - Broadcasts recording_stop to room game:{game_id}.
  - Idempotent when no recording is active (returns ok).

- POST /moderator/tokens/generate
  - Body: {"count": 1..100}
  - Returns CSV file with tokenized join links.

### Transcript

- GET /transcript
  - Query: game_id, optional limit, optional type=all|events|chat
  - Returns combined or filtered transcript output.

### WebRTC ICE / TURN

- GET /api/webrtc/ice-servers
  - Optional query: `user_id` or `role` (embedded in minted TURN username)
  - Returns browser-safe ICE config (never includes `TURN_SECRET`):
    - `mode`: `coturn` | `public_fallback` | `stun_only`
    - `iceServers`: RTCIceServer list
    - `iceTransportPolicy`: `all` | `relay`
    - `ttl` / `expires_at`: present in `coturn` mode
  - **Remote (coturn):** set `TURN_SERVER`, `TURN_PORT`, `TURN_SECRET` (same as
    coturn `static-auth-secret`) in server env.
  - **Local:** leave secret unset → public STUN/TURN fallback for LAN tests.
  - Optional env: `TURN_USE_PUBLIC_FALLBACK`, `TURN_TTL_SECONDS`,
    `TURN_TRANSPORTS`, `TURN_INCLUDE_PUBLIC_STUN`, `ICE_TRANSPORT_POLICY`.

## Socket.IO Events

### Client -> Server

- join
  - Payload: {"game_id", "role", "participant_id"}
  - Joins shared game room and role room.

- chat
  - Payload: {"game_id", "role", "participant_id", "text"}
  - Writes chat row and broadcasts message.

- voice_join
  - Payload: {"game_id", "role", "participant_id", "client_id"}
  - Registers participant in voice mesh.

- webrtc_signal
  - Payload: {"game_id", "role", "participant_id", "from_id", "to_id", "description"|"candidate"}
  - Relays WebRTC signaling data to specific peer.

### Server -> Client (selected)

- system
- chat
- peers_list
- new_peer_joined
- webrtc_signal
- card_eliminated
- eliminate
- round_complete
- roles_swapped
- recording_start
  - Payload: {"game_id", "recording_id", "server_ts"}
- recording_stop
  - Payload: {"game_id", "recording_id", "server_ts"}
- game_ended
  - Payload: {"game_id", "state"}
  - Clients should leave voice when received.

## State Model

Primary flow:

1. CLOSED
2. OPEN
3. READY
4. IN_PROGRESS
5. ENDED

Game state tracks:

- waiting_participants
- player1_id, player2_id
- round_number
- round_phase

## Data Logging Split

- events: system/session events
- chat: chat messages
- eliminated_cards: elimination facts
- rounds: secret card per round and timing
