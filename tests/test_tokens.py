import pytest
import json
import os
import datetime
import uuid

# Test with the actual MODERATOR_PASSWORD from .env
MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD", "test-password")


class TestTokenManagement:
    """Test access token validation and expiration."""
    
    def test_invalid_token_join(self, client, reset_globals):
        """Test joining with invalid token returns error."""
        res = client.post("/join/enter", json={"token": "invalid-token-xyz"})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data.get("status") == "error"
        assert "invalid" in data.get("message", "").lower()

    def test_expired_token(self, client, reset_globals):
        """Test joining with expired token returns error."""
        from app import get_db_conn
        
        # Create an expired token directly in DB
        expired_time = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        expired_token = f"expired-token-{uuid.uuid4().hex}"
        
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO access_tokens (token, created_at, expires_at) VALUES (%s, %s, %s)",
                (expired_token, datetime.datetime.now().isoformat(), expired_time)
            )
            # Context manager auto-commits
        
        # Try to join with expired token
        res = client.post("/join/enter", json={"token": expired_token})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data.get("status") == "error"
        assert "expired" in data.get("message", "").lower()

    def test_token_without_join_page(self, client, reset_globals):
        """Test accessing /join page without token shows error."""
        res = client.get("/join")
        assert res.status_code == 200
        # Should render the waiting page with an error message
        assert b"No token provided" in res.data or b"token" in res.data.lower()

    def test_valid_token_flow(self, client, reset_globals):
        """Test complete valid token flow."""
        # Setup: Create game and generate valid token
        with client.session_transaction() as sess:
            sess['moderator'] = True
        
        client.post("/moderator/control/open", json={})
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 1})
        assert tokens_res.status_code == 200
        
        # Extract token from CSV
        import csv
        import io
        from urllib.parse import urlparse, parse_qs
        
        csv_content = tokens_res.data.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        url = rows[1][0]  # Get first token URL
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        token = query_params.get('token', [None])[0]
        
        # Join with valid token should succeed
        res = client.post("/join/enter", json={"token": token})
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data.get("status") == "ok"
        assert data.get("participant_id") is not None

    def test_generated_tokens_expire_in_60_days(self, client, reset_globals):
        """Newly generated tokens are valid for 60 days."""
        from app import TOKEN_VALIDITY_DAYS, get_db_conn
        import csv
        import io
        from urllib.parse import urlparse, parse_qs

        with client.session_transaction() as sess:
            sess["moderator"] = True

        client.post("/moderator/control/open", json={})
        before = datetime.datetime.now()
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 1})
        after = datetime.datetime.now()
        assert tokens_res.status_code == 200

        csv_content = tokens_res.data.decode("utf-8")
        url = list(csv.reader(io.StringIO(csv_content)))[1][0]
        token = parse_qs(urlparse(url).query).get("token", [None])[0]

        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT expires_at FROM access_tokens WHERE token = %s",
                (token,),
            )
            expires_at = c.fetchone()["expires_at"]

        def as_naive_seconds(value):
            if hasattr(value, "tzinfo") and value.tzinfo is not None:
                value = value.replace(tzinfo=None)
            return value.replace(microsecond=0)

        # MariaDB DATETIME has second precision; datetime.now() has microseconds.
        expires_at = as_naive_seconds(expires_at)
        expected_min = as_naive_seconds(before) + datetime.timedelta(days=TOKEN_VALIDITY_DAYS)
        expected_max = as_naive_seconds(after) + datetime.timedelta(days=TOKEN_VALIDITY_DAYS)
        assert TOKEN_VALIDITY_DAYS == 60
        assert expected_min <= expires_at <= expected_max
