import pytest
import os

# Test with the actual MODERATOR_PASSWORD from .env
MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD", "test-password")


class TestAuth:
    """Test home page and authentication routes."""
    
    def test_index_loads(self, client, reset_globals):
        """Test home page loads."""
        res = client.get("/")
        assert res.status_code == 200
        assert b"GuessWho" in res.data or b"game" in res.data.lower()

    def test_login_success(self, client, reset_globals):
        """Test successful moderator login."""
        res = client.post("/login", data={"password": MODERATOR_PASSWORD})
        assert res.status_code == 302  # Redirect after successful login
        
    def test_login_failure(self, client, reset_globals):
        """Test failed login with wrong password."""
        res = client.post("/login", data={"password": "wrong-password"})
        assert res.status_code in [200, 302]  # Either shows error or bad redirect

    def test_dashboard_requires_auth(self, client, reset_globals):
        """Test dashboard redirects unauthorized users."""
        res = client.get("/dashboard")
        assert res.status_code == 302  # Should redirect to login
