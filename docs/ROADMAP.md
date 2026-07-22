# Project Roadmap – Xposed

Development milestones for the *Xposed* web application (Guess Who–style research game with live voice).

**Last updated:** July 2026

---

## Status at a glance

| Phase | Status |
|-------|--------|
| 1 – Core MVP | Done |
| 2 – First game playable | Done |
| 3 – Live voice + recording | **In progress** — voice done; **next: client MediaRecorder** |
| 4 – Deployment & security | Mostly done (hardening ongoing) |
| 5 – Research features | Future |

---

## Phase 1 – Core Functionality (MVP)

- [x] Flask backend with game APIs  
- [x] Player and moderator interfaces  
- [x] Socket.IO real-time communication  
- [x] Unique `game_id` per session  
- [x] Database logging of in-game events  
- [x] UI for character cards and interactions  

---

## Phase 2 – First Game Playable

- [x] Win condition and final-guess UI  
- [x] Card layout and responsive design  
- [x] Index page with staff login  
- [x] Moderator dashboard  
- [x] Token-based participant entry  
- [x] Export of game data (CSV / transcript APIs)  

---

## Phase 3 – Live Audio & Moderator-Controlled Recording

### Live voice (WebRTC mesh) 

- [x] `audio_events` table in SQL schema  
- [x] 3-way WebRTC mesh (moderator + player1 + player2)  
- [x] Socket.IO WebRTC signaling  
- [x] Mic check / pre-join flow; auto-join voice after mic ready  
- [x] Stale peer cleanup, voice leave / disconnect handling  
- [x] Institutional coturn TURN (`TURN_SERVER` / `TURN_SECRET`) + public fallback for local dev  
- [x] `GET /api/webrtc/ice-servers` for browser ICE config  

### Moderator recording control

- [x] Start/Stop Recording on moderator dashboard  
- [x] `POST /moderator/control/recording/start` and `…/stop`  
- [x] Broadcast `recording_start` / `recording_stop` (`recording_id`, `server_ts`)  
- [x] Recording state in game state / Redis  
- [x] pytest coverage (`tests/test_recording_control.py`)  

### Recording model (design)

Each browser records **its own microphone only** (not remote WebRTC audio).

### Audio capture & storage — in progress

**Capture:**

- [ ] MediaRecorder on player1 / player2 / moderator (local mic)  
- [ ] Auto-start / stop on `recording_start` / `recording_stop`  
- [ ] Capture `client_received_ts`, `client_recorder_start_ts`, `client_recorder_stop_ts`  
- [ ] Recording indicator UI; handle voice not joined / refresh mid-session  

**Upload & storage:**

- [ ] `POST /audio/upload` (multipart: file + metadata)  
- [ ] Path pattern: `{game_id}/{recording_id}_{role}_{participant_id}.webm`  
- [ ] Env `AUDIO_STORAGE_DIR` (local `data/audio/`; staging e.g. `/data/xposed/shared/audio/`)  
- [ ] Insert `audio_events` with path + start/end times  
- [ ] Reject uploads missing required timestamps  
- [ ] Staging directory, deploy env, full-session smoke test  

---

## Phase 4 – Production Deployment & Security

- [x] Relational DB (MySQL / MariaDB; Redis for live state)  
- [x] HTTPS (reverse proxy)  
- [x] Reverse proxy support (Apache in staging; app has ProxyFix)  
- [x] Staff passwords from environment (`MODERATOR_PASSWORD`, `AUDITOR_PASSWORD`)  
- [x] Optional Redis auth; reverse-proxy / auditor role features  
- [x] API / usage documentation (MkDocs)  
- [x] Basic pytest suite (expand over time)  
- [ ] Broader input validation and error handling  
- [ ] Stronger disconnect / reconnection recovery (game + voice)  

---

## Phase 5 – Future Features

- [ ] Speech-to-text (e.g. Whisper) on saved stems  
- [ ] Researcher analytics dashboard  
- [ ] Export analysis-ready datasets (events + audio + transcripts)  
- [ ] Offline multi-stem alignment script (`scripts/align_recordings.py`)  
- [ ] Expand automated tests (more pytest + optional Playwright)  
- [ ] Multiple concurrent moderators / sessions  

---

## Suggested order of work

1. **`feature/media-recorder`** — record local mic on all roles when moderator starts recording  
2. **`feature/audio-upload`** — upload webm + timestamps; persist `audio_events`  
3. **`chore/audio-storage-staging`** — VM directory, env, full pipeline smoke test  
4. Hardening / reconnection and research tooling as needed  

---
