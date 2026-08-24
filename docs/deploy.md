# Deploy

Apache (TLS) proxies to Gunicorn on `127.0.0.1:8000` (one gevent WebSocket worker). Redis and MariaDB hold live state and durable rows. coturn on UDP/TCP 3478 provides TURN for voice.

## Environment

Load from `.env` (or systemd `EnvironmentFile`). Never commit this file.

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask sessions (required) |
| `MODERATOR_PASSWORD` | Staff login |
| `AUDITOR_PASSWORD` | Optional read-only staff |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PWD`, `DB_NAME` | MariaDB (or `DATABASE_URL`) |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` | Live state |
| `APP_PORT` | Gunicorn bind port (often `8000`) |
| `APP_URL` | Public hostname for token links |
| `AUDIO_STORAGE_DIR` | **Filesystem** directory for stems |
| `TURN_SERVER`, `TURN_PORT`, `TURN_SECRET` | coturn (`static-auth-secret`) |

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

After `systemctl restart coturn`, expect about **two** TCP and **two** UDP listeners on 3478 — not hundreds. The app mints short-lived TURN credentials; browsers never see `TURN_SECRET`. `GET /api/webrtc/ice-servers` should report `"mode": "coturn"`.

Local development: leave `TURN_SERVER` / `TURN_SECRET` unset for public ICE fallback.

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

One take produces three stems (player1, player2, moderator). Role swap starts a second take. Metadata is in `audio_events`.

Copy off the server:

```bash
rsync -avP user@host:/path/to/audio/ ./audio/
```

Use `-e 'ssh -p <port>'` 

## Database

MariaDB listens on localhost. From a laptop, use DBeaver (or similar) with an **SSH tunnel**:

- SSH host: the VPS; auth with your key
- Database host: `127.0.0.1`, port `3306`
- User / password / database: from `.env` (`DB_*`)

Do not expose port 3306 publicly. Do not install phpMyAdmin on a small application VPS unless you have a separate, locked-down reason.
