import pytest
import json
import os
import datetime

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
        
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO access_tokens (token, created_at, expires_at) VALUES (%s, %s, %s)",
                ("expired-token", datetime.datetime.now().isoformat(), expired_time)
            )
            # Context manager auto-commits
        
        # Try to join with expired token
        res = client.post("/join/enter", json={"token": "expired-token"})
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
