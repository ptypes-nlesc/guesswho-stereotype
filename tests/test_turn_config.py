"""Unit tests for TURN credential minting and ICE config modes."""

import base64
import hashlib
import hmac

import pytest

from turn_config import (
    build_ice_config,
    coturn_urls,
    mint_turn_credentials,
    public_fallback_ice_servers,
)


def test_mint_turn_credentials_hmac():
    secret = "test-static-auth-secret"
    creds = mint_turn_credentials(secret, ttl_seconds=3600, now=1_700_000_000)
    assert creds["username"] == str(1_700_000_000 + 3600)
    expected = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            creds["username"].encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("ascii")
    assert creds["credential"] == expected
    assert creds["ttl"] == 3600
    assert creds["expires_at"] == 1_700_000_000 + 3600


def test_mint_turn_credentials_with_user_id():
    creds = mint_turn_credentials(
        "secret",
        ttl_seconds=60,
        user_id="player1",
        now=1000,
    )
    assert creds["username"] == "1060:player1"


def test_mint_requires_secret():
    with pytest.raises(ValueError):
        mint_turn_credentials("")


def test_coturn_urls():
    urls = coturn_urls("xposed-test.eur.nl", 3478, ["udp", "tcp"])
    assert "stun:xposed-test.eur.nl:3478" in urls
    assert "turn:xposed-test.eur.nl:3478?transport=udp" in urls
    assert "turn:xposed-test.eur.nl:3478?transport=tcp" in urls


def test_build_ice_config_coturn_mode():
    cfg = build_ice_config(
        user_id="moderator",
        env={
            "TURN_SERVER": "xposed-test.eur.nl",
            "TURN_PORT": "3478",
            "TURN_SECRET": "fe32secret",
            "TURN_INCLUDE_PUBLIC_STUN": "0",
            "ICE_TRANSPORT_POLICY": "all",
        },
    )
    assert cfg["mode"] == "coturn"
    assert cfg["server"] == "xposed-test.eur.nl"
    assert cfg["port"] == 3478
    assert cfg["ttl"]
    assert cfg["expires_at"]
    assert len(cfg["iceServers"]) == 1
    entry = cfg["iceServers"][0]
    assert entry["username"]
    assert entry["credential"]
    assert any(u.startswith("turn:") for u in entry["urls"])
    # Secret must never appear in the payload
    blob = str(cfg)
    assert "fe32secret" not in blob


def test_build_ice_config_public_fallback():
    cfg = build_ice_config(env={})
    assert cfg["mode"] == "public_fallback"
    assert cfg["ttl"] is None
    assert cfg["iceServers"] == public_fallback_ice_servers()


def test_build_ice_config_stun_only_when_fallback_disabled():
    cfg = build_ice_config(
        env={
            "TURN_USE_PUBLIC_FALLBACK": "0",
        }
    )
    assert cfg["mode"] == "stun_only"
    assert cfg["iceServers"][0]["urls"].startswith("stun:")


def test_build_ice_config_relay_policy():
    cfg = build_ice_config(
        env={
            "TURN_SERVER": "example.test",
            "TURN_SECRET": "s",
            "ICE_TRANSPORT_POLICY": "relay",
            "TURN_INCLUDE_PUBLIC_STUN": "0",
        }
    )
    assert cfg["iceTransportPolicy"] == "relay"


def test_ice_servers_endpoint_public_fallback(monkeypatch):
    """API returns public fallback when TURN_* is unset (no DB required)."""
    monkeypatch.delenv("TURN_SERVER", raising=False)
    monkeypatch.delenv("TURN_SECRET", raising=False)
    monkeypatch.setenv("TURN_USE_PUBLIC_FALLBACK", "1")

    from app import app

    with app.test_client() as client:
        res = client.get("/api/webrtc/ice-servers")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["mode"] == "public_fallback"
    assert isinstance(data["iceServers"], list)
    assert len(data["iceServers"]) >= 1
    assert "TURN_SECRET" not in str(data)


def test_ice_servers_endpoint_coturn(monkeypatch):
    monkeypatch.setenv("TURN_SERVER", "xposed-test.eur.nl")
    monkeypatch.setenv("TURN_PORT", "3478")
    monkeypatch.setenv("TURN_SECRET", "unit-test-secret")
    monkeypatch.setenv("TURN_INCLUDE_PUBLIC_STUN", "0")

    from app import app

    with app.test_client() as client:
        res = client.get("/api/webrtc/ice-servers?role=player1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["mode"] == "coturn"
    entry = data["iceServers"][-1]
    assert "username" in entry
    assert "credential" in entry
    assert "player1" in entry["username"]
    assert "unit-test-secret" not in str(data)
