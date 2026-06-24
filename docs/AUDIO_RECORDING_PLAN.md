# WebRTC & Voice Recording — Development Plan

Reference guide for implementing Phase 3 (moderator-controlled recording) on top of the existing WebRTC voice mesh.

**Last updated:** June 2026

###  Phase 3

- [ ] Moderator start/stop recording controls
- [ ] `recording_start` / `recording_stop` socket events
- [ ] MediaRecorder on client pages
- [ ] Upload endpoint + file storage + sync metadata
- [ ] `audio_events` rows with timestamps for later alignment

---

## Recording model: 3 separate files

Each browser records **its own microphone only** — not a mixed file, not what they hear through WebRTC.

| Client | Recorded audio | Example file |
|--------|----------------|--------------|
| Player 1 | P1 local mic | `{game_id}/{recording_id}_player1_{participant_id}.webm` |
| Player 2 | P2 local mic | `{game_id}/{recording_id}_player2_{participant_id}.webm` |
| Moderator | Moderator local mic | `{game_id}/{recording_id}_moderator_{id}.webm` |

One recording session → **3 mono files** + **3 `audio_events` rows**, linked by shared `recording_id`.

---

## Sync strategy

Sync metadata is **cheap to capture at build time** and makes later analysis reproducible. Do not defer it to a separate phase or rely on aligning waveforms by hand.

### Rule

**Never upload a file without its timestamps.**

### How alignment works

1. Server broadcasts `recording_start` with `server_ts` — this is **t = 0** for the session.
2. Each client logs when the event arrives and when `MediaRecorder` actually starts/stops.
3. On upload, client sends those timestamps with the audio blob.
4. Server stores them in `audio_events`.
5. Later analysis pads each stem to a shared timeline (see [Sync later for analysis](#sync-later-for-analysis)).

Typical offsets between clients: **50–300 ms** — sufficient for turn-taking and transcription.

### Metadata fields

| Field | Set by | Required |
|-------|--------|----------|
| `recording_id` | Server | Yes |
| `server_ts` | Server (socket event) | Yes |
| `client_recorder_start_ts` | Client (`Date.now()` at `MediaRecorder.start()`) | Yes |
| `client_recorder_stop_ts` | Client (`Date.now()` at `MediaRecorder.stop()`) | Yes |
| `client_received_ts` | Client (when socket event fires) | Recommended (debugging) |

Populate `audio_events.start_time` / `end_time` from server clock + client offsets.

### What not to build

- Real-time clock sync (NTP)
- Sample-perfect in-app alignment
- Server-side merge at record time
- Waveform cross-correlation in the app

---

## Environments

| Environment | URL / host | Purpose |
|-------------|------------|---------|
| **Local** | `http://127.0.0.1:5000` | Daily development, pytest, quick 3-tab tests |
| **Staging** | `https://xposed-test.eur.nl` | Integration testing (HTTPS, Apache proxy, TURN) |
| **Backend VM** | `t-gen-py17.app.eur.nl` — Gunicorn port **5000** | Deploy target |

### Local run command

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

Return staging to stable after testing:

```bash
git checkout main
git pull origin main
sudo systemctl restart xposed--xposed.service
```

---

## Pre-flight: WebRTC smoke test

Run **before branch 2** (media-recorder) and whenever voice behaviour is suspect. 

### Staging smoke test (~15 min)

1. Log in as moderator on `https://xposed-test.eur.nl/`.
2. Open entry → generate tokens → two participants join → start game.
3. Open **3 browser tabs**:
   - `/moderator?game_id=…`
   - `/player1?game_id=…&participant_id=…`
   - `/player2?game_id=…&participant_id=…`
4. In each tab, click **Join voice**.
5. Confirm:
   - Status shows connected peers (e.g. `2/2 connected`)
   - All three participants hear each other
   - Browser console shows `[WebRTC]` offer/answer logs without repeated errors
6. **Optional:** repeat with one client on mobile data (tests TURN / NAT).

### Red flags — fix before recording work

| Symptom | Likely cause |
|---------|----------------|
| "microphone blocked" | Browser permission / non-secure context |
| Stuck on "waiting for peers…" | Socket.IO or `voice_join` issue |
| `0/N connected` forever | Signaling not routed; check Apache WebSocket proxy |
| One-way audio | ICE / TURN / firewall |
| 404 on routes other than `/` | Apache proxy not forwarding all paths |

---

## Branch plan

Sync is folded into branches 2 and 3 — there is no separate sync branch.

```text
main
 └── 1. feature/recording-control
       └── 2. feature/media-recorder      ← capture client timestamps
             └── 3. feature/audio-upload  ← upload + sync metadata in DB
                   └── 4. chore/audio-storage-staging
```

| # | Branch | Est. effort |
|---|--------|-------------|
| 1 | `feature/recording-control` | 0.5–1 day |
| 2 | `feature/media-recorder` | 1–2 days |
| 3 | `feature/audio-upload` | 1 day |
| 4 | `chore/audio-storage-staging` | 0.5 day |

---

## Branch 1: `feature/recording-control` ← START HERE

### Goal

Moderator can start and stop a recording session. All connected clients receive socket events. **No audio files yet.**

### Work

| Area | Tasks |
|------|-------|
| **Dashboard UI** | Add "Start Recording" / "Stop Recording" buttons; enable only in `IN_PROGRESS` |
| **HTTP API** | `POST /moderator/control/recording/start` and `POST /moderator/control/recording/stop` |
| **Socket broadcast** | Emit `recording_start` / `recording_stop` to room `game:{game_id}` |
| **Payload** | `{ game_id, recording_id, server_ts }` — `server_ts` is ISO 8601 UTC |
| **Game state** | Track `recording_active` and `recording_id` in Redis |
| **Audit log** | `record_event()` for `recording_start` / `recording_stop` |
| **Docs** | Update `docs/api.md` |
| **Tests** | pytest: auth, state guards, idempotent stop |

### Files (expected)

- `app.py`
- `templates/dashboard.html`
- `docs/api.md`
- `tests/test_recording_control.py` (new)

### Test

| Where | What |
|-------|------|
| **Local** | `pytest -q` |
| **Local manual** | Start game; add temporary `socket.on('recording_start', …)` console log on player pages |
| **Staging** | Deploy branch; moderator clicks start/stop; confirm events in 3 browser consoles |

### Done when

- [ ] Buttons visible and correctly enabled/disabled by game state
- [ ] Start/stop return `{ "status": "ok" }`
- [ ] `recording_start` / `recording_stop` received in player and moderator tabs
- [ ] `server_ts` present in socket payload
- [ ] pytest passes
- [ ] Staging smoke test passes

---

## Branch 2: `feature/media-recorder`

### Goal

Clients automatically record their **local microphone** while a recording session is active. **Capture sync timestamps** ready for upload.

### Prerequisite

WebRTC smoke test passes on staging.

### Work

| Area | Tasks |
|------|-------|
| **New module** | `static/recorder.js` (or extend `webrtc.js` to expose `getLocalStream()`) |
| **Socket handlers** | `recording_start` → log `client_received_ts`, start `MediaRecorder`, log `client_recorder_start_ts`; `recording_stop` → log `client_recorder_stop_ts`, stop recorder, hold blob |
| **Integration** | Wire into `player1.html`, `player2.html`, `moderator.html` |
| **UI** | Recording indicator (e.g. "🔴 Recording…") |
| **Edge cases** | Voice not joined yet; page refresh mid-recording; stop without start |

### Notes

- MediaRecorder typically outputs **`audio/webm`**, not `.wav`. Store native format first; convert later if needed.
- Recording uses the same `localStream` as voice — voice must be joined first.
- Keep `recording_id` and `server_ts` from the socket event alongside the blob until upload.

### Test

| Where | What |
|-------|------|
| **Local** | 3-tab test: join voice → start recording → speak → stop → confirm blob + timestamps in memory (console / dev download button) |
| **Staging** | Same flow over HTTPS; check mic permission prompts |

### Done when

- [ ] All three roles record local audio during an active recording session
- [ ] Recording stops cleanly on `recording_stop`
- [ ] UI reflects recording state
- [ ] Client timestamps captured for start and stop
- [ ] No errors when voice was not joined (graceful handling)

---

## Branch 3: `feature/audio-upload`

### Goal

Persist client recordings on the server, write `audio_events` rows, and **store sync metadata** for later alignment.

### Work

| Area | Tasks |
|------|-------|
| **Endpoint** | `POST /audio/upload` (multipart) |
| **File field** | `file` |
| **Metadata fields** | `game_id`, `role`, `participant_id`, `recording_id`, `server_ts`, `client_received_ts`, `client_recorder_start_ts`, `client_recorder_stop_ts` |
| **Storage** | `AUDIO_STORAGE_DIR` env var |
| **Path pattern** | `{game_id}/{recording_id}_{role}_{participant_id}.webm` |
| **Database** | Insert into `audio_events`: `start_time`, `end_time`, `audio_path`, `participant_id` (derive times from server clock + client offsets) |
| **Validation** | Reject upload if required timestamp fields are missing |
| **Tests** | pytest: upload validation, directory creation, DB insert, timestamp storage |

### Env vars

| Variable | Local | VM |
|----------|-------|-----|
| `AUDIO_STORAGE_DIR` | `data/audio/` | `/data/xposed/shared/audio/` |

### Upload payload example

```json
{
  "game_id": "uuid",
  "role": "player1",
  "participant_id": "uuid",
  "recording_id": "uuid",
  "server_ts": "2026-06-23T10:00:00.000Z",
  "client_received_ts": 1719130800120,
  "client_recorder_start_ts": 1719130800145,
  "client_recorder_stop_ts": 1719131100302
}
```

### Test

| Where | What |
|-------|------|
| **Local** | Full flow → 3 files on disk + 3 `audio_events` rows with timestamps |
| **Staging** | Upload over HTTPS; verify files and DB on VM |
| **Sync check** | Two clients with different start delays → DB times align to shared `server_ts` |

### Done when

- [ ] Each client upload creates a file and DB row
- [ ] All required timestamp fields stored; upload rejected without them
- [ ] `audio_events.start_time` / `end_time` populated consistently
- [ ] Documented in `docs/api.md`
- [ ] pytest passes

---

## Branch 4: `chore/audio-storage-staging`

### Goal

Production-ready audio storage on the VM.

### Work

| Area | Tasks |
|------|-------|
| **VM setup** | Create audio directory; set permissions for `deploy` user |
| **Env** | Set `AUDIO_STORAGE_DIR` in `/data/xposed/shared/.env` |
| **Docs** | Update `README-dev.md` with storage path and permissions |
| **Operations** | Disk space check; optional cleanup/retention policy |

### Staging checklist

- [ ] Full session: voice + recording start/stop + 3 uploads
- [ ] 3 files exist under `AUDIO_STORAGE_DIR/{game_id}/`
- [ ] 3 `audio_events` rows with matching `recording_id` and timestamps
- [ ] Socket.IO still works through Apache after deploy
- [ ] Staging returned to `main` after feature-branch testing

---

## Sync later for analysis

After a session, alignment is a **short offline script** — not manual Audacity work, if metadata was saved.

### Workflow

```text
Export audio_events (+ events/chat) from MySQL
        ↓
Python alignment script (pandas + pydub)
        ↓
aligned_player1.wav, aligned_player2.wav, aligned_moderator.wav
        ↓
Whisper / ELAN / Praat / pandas
```

### Alignment logic

```python
# server_ts = t0 for the session
offset_ms = client_recorder_start_ts - server_ts_as_epoch_ms
aligned_track = silence(offset_ms) + audio_from_file
```

Join chat/events by converting their timestamps to seconds since `server_ts`.

### Recommended tools

| Task | Tool |
|------|------|
| Export + align stems | **Python** (`pandas`, `pydub`, ffmpeg) |
| Transcription | **Whisper** / `faster-whisper` |
| Annotation | **ELAN**, **Praat** |
| Quick listen-check | **Audacity** |
| Fallback (no metadata) | Manual Audacity or **librosa** cross-correlation — avoid |

### Optional repo addition

Add `scripts/align_recordings.py` when branch 3 is done — reads `audio_events` export, writes aligned WAVs.

---

## Optional follow-up branches

| Branch | Purpose |
|--------|---------|
| `fix/webrtc-voice-leave` | Clean up peer connections on disconnect |
| `feature/wav-conversion` | Server-side webm → wav (ffmpeg) |
| `feature/recording-status` | Dashboard shows recording state + file count |
| `feature/webrtc-reconnect` | Recover voice after page refresh |
| `scripts/align-recordings` | Offline alignment script for researchers |

---

## Testing matrix

| Layer | Local | Staging | pytest |
|-------|-------|---------|--------|
| Recording control (branch 1) | Manual (console) | Required | Required |
| MediaRecorder + timestamps (branch 2) | 3-tab manual | Required | — |
| Upload + sync metadata (branch 3) | Manual + pytest | Required | Required |
| WebRTC voice | 3-tab manual | **Required before branch 2** | — |

---

## Socket event reference

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

### Client → server

**`POST /audio/upload`** — multipart: audio file + sync metadata (see branch 3).

---
