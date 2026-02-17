import pytest

class TestAuth:
    """Test home page and authentication routes."""
    
    def test_index_loads(self, client):
        """Test home page loads."""
        res = client.get("/")
        assert res.status_code == 200
        assert b"Moderator Login" in res.data  # More precise; adjust to actual form title

    @pytest.mark.parametrize("password, expected_status, expected_redirect, expected_content", [
        ("test-password", 302, "/dashboard", None),  # Success (uses fixture override)
        ("wrong-password", 200, None, b"Invalid password"),  # Failure renders error
        ("", 200, None, b"Invalid password"),  # Empty
    ])
    def test_login(self, client, password, expected_status, expected_redirect, expected_content):
        """Test moderator login with various inputs."""
        res = client.post("/login", data={"password": password})
        assert res.status_code == expected_status
        if expected_redirect:
            assert res.location.endswith(expected_redirect)
        if expected_content:
            assert expected_content in res.data

    def test_login_success_grants_access(self, client):
        """Test successful login allows dashboard access."""
        res = client.post("/login", data={"password": "test-password"})
        assert res.status_code == 302
        assert res.location.endswith("/dashboard")
        
        # Follow-up: Session should persist
        res = client.get("/dashboard")
        assert res.status_code == 200
        assert b"Moderator Dashboard" in res.data  # Adjust to actual content

    def test_dashboard_requires_auth(self, client):
        """Test dashboard redirects unauthorized users."""
        res = client.get("/dashboard")
        assert res.status_code == 302
        assert res.location.endswith("/")  # Redirect to index/login

    def test_invalid_post_data(self, client):
        """Test login with missing or malformed data."""
        res = client.post("/login", data={})  # No password
        assert res.status_code == 200
        assert b"Invalid password" in res.data  