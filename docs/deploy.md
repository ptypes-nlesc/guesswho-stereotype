# Deploy

Apache (TLS) proxies to Gunicorn on `127.0.0.1:8000` (one gevent WebSocket worker). Do not bind Gunicorn to `0.0.0.0`. Redis and MariaDB hold live state and durable rows. coturn on UDP/TCP 3478 provides TURN for voice.

Staff session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` (unless `SESSION_COOKIE_SECURE=0`). Cookie-authenticated POSTs require a CSRF token (`X-CSRFToken` or form field `csrf_token`). `/login` and `/join/enter` are rate-limited per IP.

## Environment

Load from `.env` (or systemd `EnvironmentFile`). Never commit this file.

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask sessions (required) |
| `SESSION_COOKIE_SECURE` | Staff cookie over HTTPS only (default `1`; set `0` for local HTTP) |
| `MODERATOR_PASSWORD` | Staff login |
| `AUDITOR_PASSWORD` | Optional read-only staff |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PWD`, `DB_NAME` | MariaDB (or `DATABASE_URL`) |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` | Live state |
| `APP_PORT` | Gunicorn bind port (often `8000`) |
| `APP_URL` | Public hostname for token links and Socket.IO CORS |
| `SOCKETIO_CORS_ORIGINS` | Optional extra CORS origins (comma-separated) |
| `AUDIO_STORAGE_DIR` | **Filesystem** directory for stems |
| `AUDIO_AGE_PUBLIC_KEY` | age public key, or path to a recipients file. When set, stems are encrypted on save |
| `AUDIO_AGE_BIN` | age binary (default `age` on `PATH`) |
| `TURN_SERVER`, `TURN_PORT`, `TURN_SECRET` | coturn (`static-auth-secret`) |
| `TURN_TTL_SECONDS` | TURN credential lifetime (default 12 hours) |
| `TURN_USE_PUBLIC_FALLBACK` | Set `1` for local play without coturn |

`AUDIO_STORAGE_DIR` is a disk path writable by the Gunicorn user (for example `/home/xposed/audio`). It is not the HTTP route `/audio/upload`. A root path such as `/audio` will fail unless that directory exists and the service user can create files there.

After changing `.env`, restart Gunicorn so the process picks up new values.

```bash
sudo cat /proc/$(pgrep -n gunicorn)/environ | tr '\0' '\n' | grep AUDIO_STORAGE_DIR
```

## coturn

On a small VPS keep the thread count low so TURN cannot stall SSH and Apache:

```
listening-ip=<public-ipv4>
listening-port=3478
relay-threads=2
min-port=49152
max-port=49250
```

After `systemctl restart coturn`, expect about **two** TCP and **two** UDP listeners on 3478 — not hundreds. The app mints 12-hour TURN credentials for staff or bound players; browsers never see `TURN_SECRET`. Logged-in `GET /api/webrtc/ice-servers` should report `"mode": "coturn"`.

Local development: leave `TURN_SERVER` / `TURN_SECRET` unset and set `TURN_USE_PUBLIC_FALLBACK=1` for public ICE fallback. Without that flag the app is STUN-only.

## Health

```bash
uptime
free -h
ss -lptn | grep ':3478' | wc -l
ss -lupn | grep ':3478' | wc -l
ss -lptn | grep ':8000'
curl -sI https://<public-host> | head -5
```

Load should stay near the CPU count. A Proxy Error from Apache with frozen SSH usually means the box is CPU-starved (historically: coturn opening hundreds of 3478 sockets).

## Audio files

Layout:

```
{AUDIO_STORAGE_DIR}/{game_id}/{recording_id}_{role}_{participant}.webm
```

When `AUDIO_AGE_PUBLIC_KEY` is set, the same name is stored with `.age` appended. The browser still uploads plaintext. The server encrypts it to that public key and does not leave the `.webm` on disk. `byte_size` in `audio_events` is the plaintext size. The private key stays off the server.

One take produces three stems (player1, player2, moderator). Role swap starts a second take. Metadata is in `audio_events`.

Copy off the server:

```bash
rsync -avP user@host:/path/to/audio/ ./audio/
```

Use `-e 'ssh -p <port>'`.

Decrypt on a machine that has the matching age identity:

```bash
find ./audio -name '*.age' -print0 | while IFS= read -r -d '' f; do
  age -d -i /path/to/identity.txt -o "${f%.age}" "$f"
done
``` 

## Database

MariaDB listens on localhost. From a laptop, use DBeaver (or similar) with an **SSH tunnel**:

- SSH host: the VPS; auth with your key
- Database host: `127.0.0.1`, port `3306`
- User / password / database: from `.env` (`DB_*`)

Do not expose port 3306 publicly. Do not install phpMyAdmin on a small application VPS unless you have a separate, locked-down reason.
