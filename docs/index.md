# Xposed

Flask + Socket.IO research game for studying stereotype talk in a two-player deduction session.

A **moderator** opens a session and issues join tokens. Two **participants** play as secret-card holder and guesser, then swap roles. Voice is a three-way WebRTC mesh. Each browser records its own microphone and uploads the stem when the moderator stops (or roles swap).

## Docs

- [User guide](USAGE_GUIDE.md) — session workflow
- [API](api.md) — HTTP and Socket.IO
- [Deploy](deploy.md) — runtime, env, coturn, audio files
- [Roadmap](ROADMAP.md) — status and next work

## Architecture

| Layer | Role |
|------|------|
| Apache (or nginx) | TLS reverse proxy |
| Gunicorn (1 gevent worker) | Flask, Socket.IO |
| Redis | Live game and voice state |
| MariaDB | Games, chat, events, tokens, `audio_events` |
| coturn | TURN for WebRTC when peers cannot connect directly |

Session flow: `CLOSED` → `OPEN` → `READY` → `IN_PROGRESS` → `ENDED`.

## Local production-style run

From the project root, with dependencies from `requirements.txt`:

```bash
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 --bind 127.0.0.1:5000 --log-level info wsgi:app
```

Bind stays on localhost; put a reverse proxy in front for HTTPS. Open `http://127.0.0.1:5000/`.
