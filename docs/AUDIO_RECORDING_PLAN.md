# WebRTC & Voice Recording — Development Plan

Plan for Phase 3: moderator-controlled recording on top of the existing WebRTC voice mesh.

**Last updated:** July 2026

---

## Progress overview

| Item | Status |
|------|--------|
| Live WebRTC voice (3-way mesh) | **Done** |
| Coturn TURN + `GET /api/webrtc/ice-servers` | **Done** |
| Moderator start/stop recording (API + dashboard + socket events) | **Done** (`feature/recording-control`, merged) |
| Client MediaRecorder + timestamps | **Next** |
| Upload + `audio_events` + disk storage | Not started |
| Staging audio directory / ops | Not started |

### Phase 3 checklist

- [x] Moderator start/stop recording controls  
- [x] `recording_start` / `recording_stop` socket events (`recording_id`, `server_ts`)  
- [ ] MediaRecorder on client pages (local mic only)  
- [ ] Upload endpoint + file storage + sync metadata  
- [ ] `audio_events` rows with timestamps for later alignment  

**Start next:** [Branch 2: `feature/media-recorder`](#branch-2-featuremedia-recorder--start-here).

---

## Recording model: 3 separate files

Each browser records **its own microphone only** — not a mixed file, not remote WebRTC audio.

| Client | Recorded audio | Example file |
|--------|----------------|--------------|
| Player 1 | P1 local mic | `{game_id}/{recording_id}_player1_{participant_id}.webm` |
| Player 2 | P2 local mic | `{game_id}/{recording_id}_player2_{participant_id}.webm` |
| Moderator | Moderator local mic | `{game_id}/{recording_id}_moderator_{id}.webm` |

One recording session → **3 mono files** + **3 `audio_events` rows**, linked by shared `recording_id`.

MediaRecorder typically outputs **`audio/webm`** (not WAV). Store native format first; convert offline if needed.

---

## Sync strategy

Sync metadata is cheap at capture time and makes later analysis reproducible. Do not defer it or rely on hand-aligning waveforms.

### Rule

**Never upload a file without its timestamps.**

### How alignment works

1. Server broadcasts `recording_start` with `server_ts` — session **t = 0**.  
2. Each client logs event arrival and when `MediaRecorder` actually starts/stops.  
3. On upload, client sends those timestamps with the audio blob.  
4. Server stores them in `audio_events`.  
5. Later analysis pads each stem to a shared timeline (see [Sync later for analysis](#sync-later-for-analysis)).

Typical inter-client offsets: **50–300 ms** — enough for turn-taking and transcription.

### Metadata fields

| Field | Set by | Required |
|-------|--------|----------|
| `recording_id` | Server | Yes |
| `server_ts` | Server (socket event) | Yes |
| `client_recorder_start_ts` | Client (`Date.now()` at `MediaRecorder.start()`) | Yes |
| `client_recorder_stop_ts` | Client (`Date.now()` at `MediaRecorder.stop()`) | Yes |
| `client_received_ts` | Client (when socket event fires) | Recommended |

Populate `audio_events.start_time` / `end_time` from server clock + client offsets.

### What not to build (for v1)

- Real-time clock sync (NTP)  
- Sample-perfect in-app alignment  
- Server-side mix at record time  
- Waveform cross-correlation in the app  

---

## Environments

| Environment | URL / host | Purpose |
|-------------|------------|---------|
| **Local** | `http://127.0.0.1:5000` | Daily development, pytest, 3-tab tests |
| **Staging** | `https://xposed-test.eur.nl` | Integration (HTTPS, Apache, coturn TURN) |
| **Backend VM** | `t-gen-py17` — Gunicorn on **127.0.0.1:5000** | Deploy target |

### Local run

```bash
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 --bind 127.0.0.1:5000 --log-level info wsgi:app
```

### Staging deploy (feature branch)

```bash
cd /data/xposed/releases/current
git fetch origin
git checkout <branch-name>
git pull origin <branch-name>
sudo systemctl restart xposed--xposed.service
```

Return to stable after testing:

```bash
git checkout main
git pull origin main
sudo systemctl restart xposed--xposed.service
```

### TURN / ICE (voice prerequisite)

| Env | Role |
|-----|------|
| `TURN_SERVER` | e.g. `xposed-test.eur.nl` |
| `TURN_PORT` | e.g. `3478` |
| `TURN_SECRET` | Same as coturn `static-auth-secret` (server only) |

- Browser: `GET /api/webrtc/ice-servers` → `mode=coturn` on staging.  
- Local without coturn: leave secret unset → `mode=public_fallback`.  
- Details: [api.md](api.md) (WebRTC ICE / TURN).

---

## Pre-flight: WebRTC smoke test

Run before MediaRecorder work and whenever voice is suspect. **Voice is a prerequisite for recording** (same `localStream` / mic).

### Staging smoke test (~15 min)

1. Moderator on `https://xposed-test.eur.nl/` — open entry, tokens, two participants, start game.  
2. Three clients (tabs or devices): moderator view + player1 + player2.  
3. Complete **mic check** where required; voice should **auto-join** (Mute control, not legacy “Join voice” only).  
4. Confirm:
   - Console: `ICE config loaded mode=coturn` (on staging with TURN env set)  
   - Status e.g. `2/2 connected`  
   - Peers reach `connection state: connected`; remote tracks unmute  
   - Two-device listen test preferred over single-browser “echo”  
5. Optional: one client on mobile data (stresses NAT / TURN).

### Red flags — fix before recording capture work

| Symptom | Likely cause |
|---------|----------------|
| Microphone check / blocked | Permission or non-HTTPS context |
| `mode=public_fallback` on staging | `TURN_*` missing in app `.env` |
| `connecting` → `failed` | ICE/TURN/firewall; check for `relay` candidates if P2P fails |
| Stuck “waiting for peers” after ICE fail | See ICE status message; peer list cleared after failure |
| One-way audio | Mute state, autoplay (click page), or ICE |
| 404 on `/api/webrtc/ice-servers` via public URL from VM | Hairpin; test `http://127.0.0.1:5000/...` on VM or HTTPS from laptop |

---

## Branch plan

```text
main
 └── 1. feature/recording-control     ✅ DONE (merged)
       └── 2. feature/media-recorder  ← START HERE
             └── 3. feature/audio-upload
                   └── 4. chore/audio-storage-staging
```

| # | Branch | Status | Est. effort |
|---|--------|--------|-------------|
| 1 | `feature/recording-control` | **Done** | — |
| 2 | `feature/media-recorder` | **Next** | 1–2 days |
| 3 | `feature/audio-upload` | Pending | ~1 day |
| 4 | `chore/audio-storage-staging` | Pending | ~0.5 day |

Related voice work already on `main` (not listed as separate recording branches): WebRTC mesh, mic-check, stale-peer cleanup, coturn ICE API.

---

## Branch 1: `feature/recording-control` — done

### Goal (achieved)

Moderator starts/stops a recording session; clients receive socket events. **No audio files yet.**

### Implemented

- Dashboard Start/Stop Recording (gated by game state)  
- `POST /moderator/control/recording/start` and `…/stop`  
- Socket `recording_start` / `recording_stop` with `{ game_id, recording_id, server_ts }`  
- Game state: `recording_active`, `recording_id`  
- Audit via `record_event`  
- `tests/test_recording_control.py`  
- Documented in `docs/api.md`  

Player pages currently **log** recording events; they do not yet start MediaRecorder.

---

## Branch 2: `feature/media-recorder` ← START HERE

### Goal

Clients automatically record their **local microphone** while a recording session is active, and **capture sync timestamps** for later upload.

### Prerequisites

- [x] Recording control on `main`  
- [x] WebRTC smoke test green on staging  

### Work

| Area | Tasks |
|------|-------|
| **Module** | `static/recorder.js` and/or expose `getLocalStream()` from `webrtc.js` |
| **Socket handlers** | `recording_start` → `client_received_ts`, start MediaRecorder, `client_recorder_start_ts`; `recording_stop` → `client_recorder_stop_ts`, stop, hold blob |
| **Pages** | Wire `player1.html`, `player2.html`, `moderator.html` (replace log-only handlers) |
| **UI** | Recording indicator (e.g. “Recording…”) |
| **Edge cases** | Voice not joined yet; refresh mid-recording; stop without start |

### Notes

- Use the same mic stream as voice when possible (join voice / mic ready first).  
- Keep `recording_id` and `server_ts` from the socket event with the blob until upload (branch 3).  
- Prefer webm; do not block on server-side WAV conversion.

### Test

| Where | What |
|-------|------|
| **Local** | 3 tabs: voice → Start Recording → speak → Stop → blob + timestamps in memory (console or temp download) |
| **Staging** | Same over HTTPS; mic permissions OK |

### Done when

- [ ] All three roles record local audio during an active session  
- [ ] Clean stop on `recording_stop`  
- [ ] UI reflects recording state  
- [ ] Client start/stop timestamps captured  
- [ ] Graceful behaviour if voice was not joined  

---

## Branch 3: `feature/audio-upload`

### Goal

Persist recordings, write `audio_events`, store sync metadata for alignment.

### Work

| Area | Tasks |
|------|-------|
| **Endpoint** | `POST /audio/upload` (multipart) |
| **File field** | `file` |
| **Metadata** | `game_id`, `role`, `participant_id`, `recording_id`, `server_ts`, `client_received_ts`, `client_recorder_start_ts`, `client_recorder_stop_ts` |
| **Storage** | `AUDIO_STORAGE_DIR` |
| **Path** | `{game_id}/{recording_id}_{role}_{participant_id}.webm` |
| **DB** | Insert `audio_events` (`start_time`, `end_time`, `audio_path`, `participant_id`) |
| **Validation** | Reject if required timestamps missing |
| **Tests** | Upload validation, dirs, DB insert |

### Env

| Variable | Local | Staging VM |
|----------|-------|------------|
| `AUDIO_STORAGE_DIR` | `data/audio/` | `/data/xposed/shared/audio/` |

### Done when

- [ ] Each upload → file + DB row  
- [ ] Required timestamps stored; reject incomplete uploads  
- [ ] Documented in `docs/api.md`  
- [ ] pytest passes  

---

## Branch 4: `chore/audio-storage-staging`

### Goal

Production-ready audio storage on the VM.

### Work

| Area | Tasks |
|------|-------|
| **VM** | Create audio dir; permissions for deploy user |
| **Env** | `AUDIO_STORAGE_DIR` in shared `.env` |
| **Ops** | Disk space; optional retention policy |
| **Docs** | Deploy notes (path + permissions) |

### Staging checklist

- [ ] Full session: voice + start/stop + 3 uploads  
- [ ] 3 files under `AUDIO_STORAGE_DIR/{game_id}/`  
- [ ] 3 `audio_events` with same `recording_id` and timestamps  
- [ ] Socket.IO still works through Apache  
- [ ] Staging returned to `main` after branch tests  

---

## Sync later for analysis

Alignment is an **offline** step after sessions, if metadata was saved.

```text
Export audio_events (+ events/chat)
        ↓
Python alignment (pandas + pydub / ffmpeg)
        ↓
aligned stems per role
        ↓
Whisper / ELAN / Praat
```

```python
# server_ts = t0 for the session
offset_ms = client_recorder_start_ts - server_ts_as_epoch_ms
aligned_track = silence(offset_ms) + audio_from_file
```

| Task | Tool |
|------|------|
| Export + align | Python (`pandas`, `pydub`, ffmpeg) |
| Transcription | Whisper / faster-whisper |
| Annotation | ELAN, Praat |
| Quick check | Audacity |

Optional later: `scripts/align_recordings.py` after branch 3.

---

## Optional follow-ups

| Topic | Purpose |
|-------|---------|
| WAV conversion | Server or offline webm → wav |
| Recording status UI | Dashboard file count / per-role upload status |
| Voice reconnect | Recover mesh after refresh |
| Offline align script | Researcher packaging |

---

## Testing matrix

| Layer | Local | Staging | pytest |
|-------|-------|---------|--------|
| Recording control | Manual | Done | Done |
| WebRTC voice + TURN | Manual | **Required before MediaRecorder** | ICE unit tests |
| MediaRecorder + timestamps | 3-tab manual | Required | — |
| Upload + metadata | Manual + pytest | Required | Required |

---

## Socket / API reference (recording)

### Server → client

**`recording_start`**

```json
{
  "game_id": "uuid",
  "recording_id": "uuid",
  "server_ts": "2026-06-23T10:00:00.000Z"
}
```

**`recording_stop`**

```json
{
  "game_id": "uuid",
  "recording_id": "uuid",
  "server_ts": "2026-06-23T10:05:00.000Z"
}
```

### Client → server (branch 3)

**`POST /audio/upload`** — multipart: audio file + sync metadata.

### Moderator HTTP (done)

- `POST /moderator/control/recording/start`  
- `POST /moderator/control/recording/stop`  

See [api.md](api.md) for full API notes.

---
