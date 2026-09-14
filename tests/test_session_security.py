"""Staff session cookies, CSRF, and security headers."""

import re

from app import app


def _csrf_from_login_page(client):
    page = client.get("/")
    html = page.data.decode()
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


class TestSessionSecurity:
    def test_index_sets_security_headers(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("Referrer-Policy") == "no-referrer"
        assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "microphone=(self)" in (res.headers.get("Permissions-Policy") or "")

    def test_login_sets_httponly_lax_cookie(self, client):
        res = client.post(
            "/login",
            data={"password": "test-password", "role": "moderator"},
        )
        assert res.status_code == 302
        cookie_header = ";".join(res.headers.getlist("Set-Cookie"))
        lowered = cookie_header.lower()
        assert "httponly" in lowered
        assert "samesite=lax" in lowered
        assert "secure" not in lowered  # tests run over HTTP

    def test_login_without_csrf_fails_when_enabled(self, client):
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            res = client.post(
                "/login",
                data={"password": "test-password", "role": "moderator"},
            )
            assert res.status_code == 400
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_login_with_csrf_succeeds_when_enabled(self, client):
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            token = _csrf_from_login_page(client)
            res = client.post(
                "/login",
                data={
                    "password": "test-password",
                    "role": "moderator",
                    "csrf_token": token,
                },
            )
            assert res.status_code == 302
            assert res.location.endswith("/dashboard")
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_moderator_post_without_csrf_fails_when_enabled(self, client):
        client.post("/login", data={"password": "test-password", "role": "moderator"})
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            res = client.post("/moderator/control/open", json={})
            assert res.status_code == 400
            body = res.get_json()
            assert body["status"] == "error"
            assert "csrf" in body["message"].lower()
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_post_logout_clears_session(self, client):
        client.post("/login", data={"password": "test-password", "role": "moderator"})
        res = client.post("/logout")
        assert res.status_code == 302
        dash = client.get("/dashboard")
        assert dash.status_code == 302
        assert dash.location.endswith("/")

