"""Regression tests for session stickiness and token consumption on join."""

import csv
import io
import json
from urllib.parse import parse_qs, urlparse


class TestSessionJoinAdmission:
    """Bugs: dashboard reload cleared session; join burned tokens when entry closed."""

    def moderator_login(self, client):
        with client.session_transaction() as sess:
            sess["moderator"] = True
            sess["role"] = "moderator"
        return client

    @staticmethod
    def extract_tokens_from_csv(csv_response_data):
        csv_content = csv_response_data.decode("utf-8")
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        tokens = []
        for row in rows[1:]:
            url = row[0]
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            token = query_params.get("token", [None])[0]
            if token:
                tokens.append(token)
        return tokens

    @staticmethod
    def token_used_at(token):
        from app import get_db_conn

        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT used_at FROM access_tokens WHERE token = %s",
                (token,),
            )
            row = c.fetchone()
            return row["used_at"] if row else "missing"

    def test_dashboard_reload_keeps_open_session_game_id(self, client, reset_globals):
        """Reloading /dashboard must not drop moderator_session_game_id for OPEN games."""
        from app import get_game_state

        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        assert res_open.status_code == 200
        game_id = json.loads(res_open.data)["game_id"]
        assert get_game_state(game_id)["state"] == "OPEN"

        # Visiting the dashboard previously cleared the session binding.
        res_dash = client.get("/dashboard")
        assert res_dash.status_code == 200

        with client.session_transaction() as sess:
            assert sess.get("moderator_session_game_id") == game_id

        # Status and a second "open" must stay on the same game.
        status = json.loads(client.get("/moderator/control/status").data)
        assert status["status"] == "ok"
        assert status["game_id"] == game_id
        assert status["state"] == "OPEN"

        res_open2 = client.post("/moderator/control/open", json={})
        assert res_open2.status_code == 200
        assert json.loads(res_open2.data)["game_id"] == game_id
        assert get_game_state(game_id)["state"] == "OPEN"

    def test_dashboard_reload_keeps_ready_session(self, client, reset_globals):
        """READY sessions must also survive dashboard reload (pre-start)."""
        from app import get_game_state

        self.moderator_login(client)
        game_id = json.loads(client.post("/moderator/control/open", json={}).data)[
            "game_id"
        ]
        tokens = self.extract_tokens_from_csv(
            client.post("/moderator/tokens/generate", json={"count": 2}).data
        )
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        assert get_game_state(game_id)["state"] == "READY"

        assert client.get("/dashboard").status_code == 200
        with client.session_transaction() as sess:
            assert sess.get("moderator_session_game_id") == game_id

        status = json.loads(client.get("/moderator/control/status").data)
        assert status["game_id"] == game_id
        assert status["state"] == "READY"

    def test_join_without_open_session_does_not_consume_token(
        self, client, reset_globals
    ):
        """Token must remain reusable if join fails because there is no OPEN entry."""
        self.moderator_login(client)
        # Tokens do not require an open session; join does.
        tokens = self.extract_tokens_from_csv(
            client.post("/moderator/tokens/generate", json={"count": 1}).data
        )
        token = tokens[0]
        assert self.token_used_at(token) is None

        res = client.post("/join/enter", json={"token": token})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data["status"] == "error"
        assert "session" in data["message"].lower() or "open" in data["message"].lower()

        # Critical: token still unused
        assert self.token_used_at(token) is None

        # After opening entry, same token must work
        open_res = client.post("/moderator/control/open", json={})
        assert open_res.status_code == 200
        join_res = client.post("/join/enter", json={"token": token})
        assert join_res.status_code == 200
        assert json.loads(join_res.data)["status"] == "ok"
        assert self.token_used_at(token) is not None

    def test_join_when_entry_not_open_does_not_consume_token(
        self, client, reset_globals
    ):
        """If session exists but is not OPEN, failed join must not burn the token."""
        from app import get_game_state, set_game_state

        self.moderator_login(client)
        game_id = json.loads(client.post("/moderator/control/open", json={}).data)[
            "game_id"
        ]
        tokens = self.extract_tokens_from_csv(
            client.post("/moderator/tokens/generate", json={"count": 1}).data
        )
        token = tokens[0]

        # Force closed entry while session id is still current
        state = get_game_state(game_id)
        state["state"] = "CLOSED"
        set_game_state(game_id, state)

        res = client.post("/join/enter", json={"token": token})
        assert res.status_code == 400
        assert "open" in json.loads(res.data)["message"].lower()
        assert self.token_used_at(token) is None

        # Re-open and use the same token
        state = get_game_state(game_id)
        state["state"] = "OPEN"
        state["waiting_participants"] = []
        set_game_state(game_id, state)

        join_res = client.post("/join/enter", json={"token": token})
        assert join_res.status_code == 200
        assert json.loads(join_res.data)["status"] == "ok"
        assert self.token_used_at(token) is not None
