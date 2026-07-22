"""TURN / ICE configuration for WebRTC.

Supports two modes driven by environment variables:

1. **Institutional coturn** (remote / VPN test)::

       TURN_SERVER=xposed-test.eur.nl
       TURN_PORT=3478
       TURN_SECRET=<same as coturn static-auth-secret>

   Mints time-limited credentials (coturn ``use-auth-secret`` / TURN REST).

2. **Public fallback** (local mesh on a LAN / same machine)::

       TURN_SERVER and TURN_SECRET unset (or empty)
       TURN_USE_PUBLIC_FALLBACK=1   # default when secret missing

   Uses Google STUN + public openrelay TURN (no server secret).

The shared secret must never be sent to the browser — only short-lived
username/credential pairs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any, Dict, List, Optional


# Public servers for local / unrestricted networks (no app secret).
PUBLIC_STUN_URL = "stun:stun.l.google.com:19302"
PUBLIC_TURN_URLS = [
    "turn:openrelay.metered.ca:80",
    "turn:openrelay.metered.ca:443",
    "turn:openrelay.metered.ca:443?transport=tcp",
]
PUBLIC_TURN_USERNAME = "openrelayproject"
PUBLIC_TURN_CREDENTIAL = "openrelayproject"

DEFAULT_TURN_PORT = 3478
DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def mint_turn_credentials(
    secret: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    user_id: Optional[str] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Create coturn ``use-auth-secret`` username/credential.

    Username is ``<expiry_unix>`` or ``<expiry_unix>:<user_id>``.
    Credential is Base64(HMAC-SHA1(secret, username)).
    """
    if not secret:
        raise ValueError("TURN secret is required to mint credentials")

    ttl = max(60, int(ttl_seconds))
    expiry = int(now if now is not None else time.time()) + ttl
    if user_id:
        safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in "-_")[:64]
        username = f"{expiry}:{safe_id}" if safe_id else str(expiry)
    else:
        username = str(expiry)

    digest = hmac.new(
        secret.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    credential = base64.b64encode(digest).decode("ascii")

    return {
        "username": username,
        "credential": credential,
        "ttl": ttl,
        "expires_at": expiry,
    }


def coturn_urls(server: str, port: int, transports: Optional[List[str]] = None) -> List[str]:
    """Build stun/turn URL list for a coturn host (kept small for browser ICE limits)."""
    host = server.strip()
    if not host:
        return []
    p = int(port) if port else DEFAULT_TURN_PORT
    urls = [f"stun:{host}:{p}"]
    tlist = transports or ["udp", "tcp"]
    for transport in tlist:
        t = transport.strip().lower()
        if t == "udp":
            urls.append(f"turn:{host}:{p}?transport=udp")
        elif t == "tcp":
            urls.append(f"turn:{host}:{p}?transport=tcp")
        elif t:
            urls.append(f"turn:{host}:{p}?transport={t}")
    return urls


def public_fallback_ice_servers() -> List[Dict[str, Any]]:
    """ICE servers for local testing without institutional coturn."""
    return [
        {"urls": PUBLIC_STUN_URL},
        {
            "urls": list(PUBLIC_TURN_URLS),
            "username": PUBLIC_TURN_USERNAME,
            "credential": PUBLIC_TURN_CREDENTIAL,
        },
    ]


def build_ice_config(
    *,
    user_id: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a browser-safe ICE config from environment.

    Returns a dict suitable for JSON::

        {
          "mode": "coturn" | "public_fallback",
          "iceServers": [...],
          "iceTransportPolicy": "all" | "relay",
          "ttl": int | null,
          "expires_at": int | null,
        }

    Never includes TURN_SECRET.
    """
    # Allow tests to inject env without mutating os.environ permanently.
    def get(name: str, default: Optional[str] = None) -> Optional[str]:
        if env is not None:
            if name not in env or env[name] in (None, ""):
                return default
            return env[name]
        return _env(name, default)

    def get_bool(name: str, default: bool) -> bool:
        if env is not None:
            if name not in env or env[name] in (None, ""):
                return default
            return str(env[name]).strip().lower() in ("1", "true", "yes", "on")
        return _env_bool(name, default)

    def get_int(name: str, default: int) -> int:
        if env is not None:
            raw = env.get(name)
            if raw in (None, ""):
                return default
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default
        return _env_int(name, default)

    server = get("TURN_SERVER")
    secret = get("TURN_SECRET")
    port = get_int("TURN_PORT", DEFAULT_TURN_PORT)
    ttl = get_int("TURN_TTL_SECONDS", DEFAULT_TTL_SECONDS)
    policy = (get("ICE_TRANSPORT_POLICY", "all") or "all").strip().lower()
    if policy not in ("all", "relay"):
        policy = "all"

    use_public = get_bool("TURN_USE_PUBLIC_FALLBACK", True)
    include_public_stun = get_bool("TURN_INCLUDE_PUBLIC_STUN", True)

    # Optional explicit URL list (comma-separated), advanced override.
    custom_urls_raw = get("TURN_URLS")
    transports_raw = get("TURN_TRANSPORTS", "udp,tcp") or "udp,tcp"
    transports = [t.strip() for t in transports_raw.split(",") if t.strip()]

    if server and secret:
        if custom_urls_raw:
            urls = [u.strip() for u in custom_urls_raw.split(",") if u.strip()]
        else:
            urls = coturn_urls(server, port, transports)

        creds = mint_turn_credentials(secret, ttl_seconds=ttl, user_id=user_id)
        ice_servers: List[Dict[str, Any]] = []
        if include_public_stun:
            ice_servers.append({"urls": PUBLIC_STUN_URL})
        # One entry: coturn STUN + TURN URLs share the minted credentials.
        ice_servers.append(
            {
                "urls": urls,
                "username": creds["username"],
                "credential": creds["credential"],
            }
        )
        return {
            "mode": "coturn",
            "iceServers": ice_servers,
            "iceTransportPolicy": policy,
            "ttl": creds["ttl"],
            "expires_at": creds["expires_at"],
            "server": server,
            "port": port,
        }

    if not use_public:
        # Explicit: no coturn config and fallback disabled.
        ice_servers = [{"urls": PUBLIC_STUN_URL}]
        return {
            "mode": "stun_only",
            "iceServers": ice_servers,
            "iceTransportPolicy": policy,
            "ttl": None,
            "expires_at": None,
            "server": None,
            "port": None,
        }

    return {
        "mode": "public_fallback",
        "iceServers": public_fallback_ice_servers(),
        "iceTransportPolicy": policy,
        "ttl": None,
        "expires_at": None,
        "server": None,
        "port": None,
    }
