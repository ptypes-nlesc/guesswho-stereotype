![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)
![Socket.IO](https://img.shields.io/badge/Socket.IO-Realtime-green?logo=socketdotio)
![Redis](https://img.shields.io/badge/Redis-Cache-red?logo=redis)
![License](https://img.shields.io/badge/License-Apache%202.0-orange)
[![CI](https://github.com/ptypes-nlesc/guesswho-stereotype/actions/workflows/pytest.yml/badge.svg)](https://github.com/ptypes-nlesc/guesswho-stereotype/actions/workflows/pytest.yml)

# GuessWho Stereotype (Xposed)

Research web app for studying how people express stereotypes in a two-player deduction game (Guess Who–style). Moderators run sessions; participants join via one-time tokens. Chat, voice, and game events are logged for analysis.

## How it works

- **Player 1 (secret holder)** draws a secret character and answers questions.  
- **Player 2 (guesser)** sees a grid of characters, asks feature-based questions, and eliminates cards.  
- After round 1, **roles swap**. A **moderator** observes, can chat, and controls session flow and recording.  
- Optional **read-only auditor** staff role for low-privilege access.

## Features (current)

| Area | What exists |
|------|-------------|
| **Sessions** | Moderator dashboard: open entry, tokens, start / end / reset, role swap |
| **Access** | One-time join tokens; staff login (`MODERATOR_PASSWORD`, `AUDITOR_PASSWORD`) |
| **Realtime** | Socket.IO chat, game events, voice signaling |
| **Voice** | 3-way WebRTC mesh; mic check; auto-join; mute; coturn TURN via `GET /api/webrtc/ice-servers` |
| **Recording control** | Moderator start/stop; `recording_start` / `recording_stop` to all roles (client capture/upload still planned) |
| **Data** | MySQL/MariaDB persistence; Redis for live game/voice state |
| **Deploy** | Gunicorn + gevent WebSocket worker; reverse-proxy friendly (ProxyFix) |

Roadmap and next steps (e.g. MediaRecorder + audio upload): [docs/ROADMAP.md](docs/ROADMAP.md).  
User guide, API, and more: [docs/](docs/) (MkDocs).

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | HTML, JavaScript (Socket.IO client, WebRTC) |
| Backend | Flask 3 + Flask-SocketIO |
| Database | MySQL / MariaDB |
| Live state | Redis (optional in-memory fallback where implemented) |
| Voice | WebRTC mesh; TURN (coturn) or public ICE fallback |
| Runtime | Gunicorn + `GeventWebSocketWorker` |

## Run locally (minimal)

**Needs:** Python 3.13+, MySQL/MariaDB, Redis (recommended).

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` in the project root (required at minimum):

```env
SECRET_KEY=change-me
MODERATOR_PASSWORD=change-me
# DB_* or DATABASE_URL — see docs / deploy .env examples
# REDIS_HOST=localhost
# Optional voice: omit TURN_* for public ICE fallback; set TURN_SERVER + TURN_SECRET for coturn
```

```bash
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 --bind 127.0.0.1:5000 --log-level info wsgi:app
```

Open **http://127.0.0.1:5000/** — staff login → dashboard → open entry / tokens → participants on `/join` → start game.

Voice and full staging deploy (Apache, coturn, WireGuard/GSA) are covered in the docs and environment-specific notes, not here.

## Tests

```bash
pytest -q
```

CI runs the same suite via GitHub Actions.

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

<p>
  <img src="static/example1.png" alt="Game UI example" width="280">
  <img src="static/example2.png" alt="Game UI example" width="280">
  <img src="static/example3.png" alt="Game UI example" width="280">
</p>
