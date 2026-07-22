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

Detailed implementation plan: [AUDIO_RECORDING_PLAN.md](AUDIO_RECORDING_PLAN.md).

### Live voice (WebRTC mesh) — done

- [x] `audio_events` table in SQL schema  
- [x] 3-way WebRTC mesh (moderator + player1 + player2)  
- [x] Socket.IO WebRTC signaling  
- [x] Mic check / pre-join flow; auto-join voice after mic ready  
- [x] Stale peer cleanup, voice leave / disconnect handling  
- [x] Institutional coturn TURN (`TURN_SERVER` / `TURN_SECRET`) + public fallback for local dev  
- [x] `GET /api/webrtc/ice-servers` for browser ICE config  

### Moderator recording control — done

- [x] Start/Stop Recording on moderator dashboard  
- [x] `POST /moderator/control/recording/start` and `…/stop`  
- [x] Broadcast `recording_start` / `recording_stop` (with `recording_id`, `server_ts`)  
- [x] Recording state in game state / Redis  
- [x] pytest coverage (`tests/test_recording_control.py`)  

### Audio capture & storage — **next**

- [ ] **Client MediaRecorder** on player1 / player2 / moderator (local mic only)  
- [ ] Auto-start / stop on `recording_start` / `recording_stop`  
- [ ] Capture sync timestamps on the client  
- [ ] `POST /audio/upload` + files under `AUDIO_STORAGE_DIR`  
- [ ] Write `audio_events` rows with paths and sync metadata  
- [ ] Staging storage path / permissions on the VM  

**Immediate next implementation branch:** `feature/media-recorder`  
(see [AUDIO_RECORDING_PLAN.md](AUDIO_RECORDING_PLAN.md) § Branch 2).

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
- [ ] Expand automated tests (more pytest + optional Playwright)  
- [ ] Multiple concurrent moderators / sessions  
- [ ] Offline alignment script for multi-stem sync (`scripts/align_recordings.py`)  

---

## Suggested order of work (near term)

1. **`feature/media-recorder`** — record local mic on all roles when moderator starts recording  
2. **`feature/audio-upload`** — upload webm + timestamps; persist `audio_events`  
3. **`chore/audio-storage-staging`** — VM directory, env, smoke test full pipeline  
4. Hardening / reconnection and research tooling as needed  

---
