# GuessWho Stereotype Documentation

A lightweight research game for studying stereotype patterns through role-based gameplay.

## What this project is

GuessWho Stereotype (Xposed) is a Flask + Socket.IO application with:

- Moderator-controlled sessions
- Token-based participant access
- Two-player role flow (player1 and player2)
- Live chat and optional voice signaling
- Full audit-friendly logging into MySQL

## Documentation map

- User Guide: moderator and participant workflows
- API Reference: endpoints, sockets, and key payloads
- Roadmap: implementation status and future phases

## Architecture snapshot

- Backend: Flask + Flask-SocketIO
- Runtime state: Redis (with in-memory fallback)
- Persistence: MySQL (games, rounds, chat, events, eliminations, tokens)
- Realtime: Socket.IO and WebRTC signaling

## Run with Gunicorn

For a production-style local run, start the app through the Eventlet-enabled WSGI entrypoint:

```bash
gunicorn --worker-class eventlet -w 1 --bind 127.0.0.1:5000 --log-level info wsgi:app
```

Notes:

- Run this from the project root after installing dependencies from `requirements.txt`.
- `--worker-class eventlet` is required for WebSocket traffic to work correctly with Flask-SocketIO.
- `--bind 127.0.0.1:5000` restricts the server to localhost; use a reverse proxy (Apache/nginx) to expose it externally.
- Open `http://127.0.0.1:5000/` after the server starts.

## Notes

- Token links are one-time use.
- Session state progression: CLOSED -> OPEN -> READY -> IN_PROGRESS -> ENDED.
- Moderator is authenticated by session, not a participant identity.
