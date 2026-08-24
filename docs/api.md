# API reference

JSON bodies use `{"status": "ok", ...}` or `{"status": "error", "message": "..."}`. Participant routes take `game_id` and `participant_id`. Moderator control routes require a staff session.

## HTTP

### Session

- `GET /` — staff login
- `POST /login` — `password`, optional `role` (`moderator` or `auditor`)
- `GET /logout`
- `GET /game/status` — query `game_id`, optional `participant_id`

### Participants

- `GET /join` — query `token`
- `GET /join/status` — optional `participant_id`
- `POST /join/enter` — `{"token": "..."}`

### Players

- `GET /player1`, `GET /player2` — query `game_id`, `participant_id`
- `POST /eliminate_card` — `{"game_id", "card_id"}`

### Moderator

- `GET /dashboard`
- `GET /moderator` — query `game_id`
- `GET /moderator/control` — redirects to dashboard
- `GET /moderator/control/status`
- `POST /moderator/control/open`
- `POST /moderator/control/close`
- `POST /moderator/control/start` — `READY` → `IN_PROGRESS`
- `POST /moderator/control/end` — `IN_PROGRESS` → `ENDED`
- `POST /moderator/control/swap_roles`
- `POST /moderator/control/reset` — `CLOSED`
- `POST /moderator/tokens/generate` — `{"count": 1..100}`, returns CSV

### Recording

- `POST /moderator/control/recording/start` — while `IN_PROGRESS`. Broadcasts `recording_start` (`recording_id`, `server_ts`). Clients start MediaRecorder.
- `POST /moderator/control/recording/stop` — broadcasts `recording_stop`. Idempotent if already idle. Clients POST stems to `/audio/upload`.
- `POST /audio/upload` — multipart:
  - required: `file`, `game_id`, `recording_id`, `role`, `client_received_ts`, `client_recorder_start_ts`, `client_recorder_stop_ts`
  - optional: `participant_id` (required for players), `server_ts`, `server_stop_ts`, `mime_type`
  - players must be assigned to the game; moderator needs a staff session
  - stores `{AUDIO_STORAGE_DIR}/{game_id}/{recording_id}_{role}_{participant}.webm`
  - upserts `audio_events` on `(game_id, recording_id, role)`
  - emits `audio_upload_complete`; updates `last_audio_uploads`

### Transcript and ICE

- `GET /transcript` — query `game_id`, optional `limit`, `type=all|events|chat`
- `GET /api/webrtc/ice-servers` — optional `user_id` or `role`. Returns `mode`, `iceServers`, `iceTransportPolicy`. Never includes `TURN_SECRET`.

## Socket.IO

**Client → server:** `join`, `chat`, `voice_join`, `webrtc_signal`

**Server → client (selected):** `system`, `chat`, `peers_list`, `new_peer_joined`, `webrtc_signal`, `card_eliminated`, `eliminate`, `round_complete`, `roles_swapped`, `game_ended`

- `recording_start` / `recording_stop` — `{game_id, recording_id, server_ts}`
- `audio_upload_complete` — `{game_id, recording_id, role, participant_id, audio_path, byte_size, audio_event_id}`

## State

`CLOSED` → `OPEN` → `READY` → `IN_PROGRESS` → `ENDED`

Live game state includes `waiting_participants`, `player1_id`, `player2_id`, `round_number`, `round_phase`, recording flags, `last_audio_uploads`.

## Tables

| Table | Content |
|-------|---------|
| `events` | Session / system actions |
| `chat` | Messages |
| `eliminated_cards` | Eliminations |
| `rounds` | Secret card and timing |
| `audio_events` | Stem path, timestamps, byte size |
| `access_tokens` | Join tokens |
