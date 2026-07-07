import csv
import io
import json
from urllib.parse import parse_qs, urlparse


AUDITOR_PASSWORD = "test-auditor-password"
MODERATOR_PASSWORD = "test-password"


class TestAuditorAuth:
    """Read-only auditor login and access controls."""

    def extract_tokens_from_csv(self, csv_bytes):
        csv_reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8")))
        rows = list(csv_reader)
        tokens = []
        for row in rows[1:]:
            parsed = urlparse(row[0])
            token = parse_qs(parsed.query).get("token", [None])[0]
            assert token is not None
            tokens.append(token)
        return tokens

    def auditor_login(self, client):
        return client.post(
            "/login",
            data={"password": AUDITOR_PASSWORD, "role": "auditor"},
        )

    def moderator_login(self, client):
        return client.post(
            "/login",
            data={"password": MODERATOR_PASSWORD, "role": "moderator"},
        )

    def test_auditor_login_success(self, client):
        res = self.auditor_login(client)
        assert res.status_code == 302
        assert res.location.endswith("/dashboard")

        res = client.get("/dashboard")
        assert res.status_code == 200
        assert b"Read-only auditor mode" in res.data

    def test_auditor_login_rejects_wrong_password(self, client):
        res = client.post(
            "/login",
            data={"password": "wrong-password", "role": "auditor"},
        )
        assert res.status_code == 200
        assert b"Invalid password" in res.data

    def test_auditor_cannot_access_dashboard_without_login(self, client):
        res = client.get("/dashboard")
        assert res.status_code == 302
        assert res.location.endswith("/")

    def test_auditor_can_read_status(self, client, reset_globals):
        self.auditor_login(client)
        res = client.get("/moderator/control/status")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "no_session"

    def test_auditor_cannot_open_entry(self, client, reset_globals):
        self.auditor_login(client)
        res = client.post("/moderator/control/open", json={})
        assert res.status_code == 403

    def test_auditor_cannot_generate_tokens(self, client, reset_globals):
        self.auditor_login(client)
        res = client.post("/moderator/tokens/generate", json={"count": 1})
        assert res.status_code == 403

    def test_auditor_cannot_start_or_end_game(self, client, reset_globals):
        self.auditor_login(client)
        assert client.post("/moderator/control/start", json={}).status_code == 403
        assert client.post("/moderator/control/end", json={}).status_code == 403

    def test_auditor_can_view_active_session(self, client, reset_globals):
        self.moderator_login(client)
        open_res = client.post("/moderator/control/open", json={})
        game_id = json.loads(open_res.data)["game_id"]
        client.get("/logout")

        self.auditor_login(client)
        res = client.get(f"/moderator?game_id={game_id}")
        assert res.status_code == 200
        assert b"Observer View" in res.data

    def test_auditor_cannot_view_other_game_id(self, client, reset_globals):
        self.moderator_login(client)
        open_res = client.post("/moderator/control/open", json={})
        active_game_id = json.loads(open_res.data)["game_id"]
        client.get("/logout")

        self.auditor_login(client)
        other_game_id = "deadbeef" * 4
        res = client.get(f"/moderator?game_id={other_game_id}")
        assert res.status_code == 403

        res = client.get(f"/transcript?game_id={active_game_id}&limit=50")
        assert res.status_code == 200

    def test_auditor_transcript_includes_eliminations(self, client, reset_globals):
        self.moderator_login(client)
        open_res = client.post("/moderator/control/open", json={})
        game_id = json.loads(open_res.data)["game_id"]

        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        client.post("/eliminate_card", json={"game_id": game_id, "card_id": 4})

        client.get("/logout")
        self.auditor_login(client)

        transcript_res = client.get(f"/transcript?game_id={game_id}&limit=200")
        entries = json.loads(transcript_res.data)
        assert any(
            entry.get("action") == "eliminate" and entry.get("card") == 4
            for entry in entries
        )

    def test_auditor_socket_chat_is_read_only(self, test_db, reset_globals):
        from app import app, socketio, get_chat_history

        from app import app

        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"
        flask_client = app.test_client()
        flask_client.post(
            "/login",
            data={"password": MODERATOR_PASSWORD, "role": "moderator"},
        )
        open_res = flask_client.post("/moderator/control/open", json={})
        game_id = json.loads(open_res.data)["game_id"]
        flask_client.get("/logout")

        flask_client.post(
            "/login",
            data={"password": AUDITOR_PASSWORD, "role": "auditor"},
        )
        socketio_client = socketio.test_client(app, flask_test_client=flask_client)
        try:
            join_ack = socketio_client.emit(
                "join", {"game_id": game_id, "role": "auditor"}, callback=True
            )
            assert join_ack != {"status": "error", "message": "Unauthorized"}
            socketio_client.emit(
                "chat",
                {"game_id": game_id, "role": "auditor", "text": "should not send"},
            )

            chat_history = get_chat_history(game_id)
            assert not any(
                entry.get("text") == "should not send" for entry in chat_history
            )
        finally:
            socketio_client.disconnect()