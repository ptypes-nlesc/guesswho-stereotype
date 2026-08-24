# Roadmap

**Last updated:** August 2026

| Phase | Status |
|-------|--------|
| 1 – Core MVP | Done |
| 2 – First game playable | Done |
| 3 – Live voice + recording | Done |
| 4 – Deployment & security | Mostly done |
| 5 – Research features | Future |

## Phase 1 – Core

- [x] Flask APIs, player and moderator UI
- [x] Socket.IO
- [x] Per-session `game_id`
- [x] Event logging
- [x] Character cards

## Phase 2 – Playable session

- [x] Win / final-guess UI
- [x] Staff login and moderator dashboard
- [x] Token-based entry
- [x] Transcript / CSV export

## Phase 3 – Voice and recording

Each browser records **its own microphone** (not remote WebRTC audio).

- [x] Three-way WebRTC mesh; mic check; mute; stale-peer cleanup
- [x] coturn TURN (`TURN_SERVER` / `TURN_SECRET`) and public ICE fallback
- [x] `GET /api/webrtc/ice-servers`
- [x] Moderator start/stop recording; `recording_start` / `recording_stop`
- [x] MediaRecorder on player1, player2, moderator
- [x] `POST /audio/upload`; files under `AUDIO_STORAGE_DIR/{game_id}/`
- [x] `audio_events` rows; dashboard stem checklist
- [x] Segment on role swap; wait for own upload before navigation
- [x] Deploy path and full-session smoke test (writable `AUDIO_STORAGE_DIR`)

## Phase 4 – Deploy and security

- [x] MariaDB + Redis
- [x] HTTPS reverse proxy (ProxyFix)
- [x] Staff passwords from the environment
- [x] MkDocs + pytest
- [ ] Stronger input validation
- [ ] Stronger reconnect recovery (game and voice)

## Phase 5 – Research tooling

- [ ] Speech-to-text on saved stems
- [ ] Researcher analytics
- [ ] Export of aligned events + audio + transcripts
- [ ] Offline multi-stem alignment
- [ ] Broader automated tests
- [ ] Multiple concurrent moderators / sessions
