"""Unauthenticated and mis-bound clients must not see game or research data."""

import csv
import io
import json
from urllib.parse import parse_qs, urlparse


class TestUnauthenticatedSurface:
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
            token = parse_qs(parsed.query).get("token", [None])[0]
            if token:
                tokens.append(token)
        return tokens

    def _start_in_progress(self, client):
        from app import get_game_state

        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        res1 = client.post("/join/enter", json={"token": tokens[0]})
        res2 = client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        game_state = get_game_state(game_id)
        return {
            "game_id": game_id,
            "player1_id": json.loads(res1.data)["participant_id"],
            "player2_id": json.loads(res2.data)["participant_id"],
            "game_state": game_state,
        }

    def test_create_game_route_removed(self, client, reset_globals):
        res = client.post("/create_game", json={})
        assert res.status_code == 404

    def test_player1_without_participant_id_is_forbidden(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.get(f"/player1?game_id={session['game_id']}")
        assert res.status_code == 400
        assert b"static/cards/" not in res.data

    def test_player1_without_query_does_not_leak_secret_card(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.get(f"/player1?game_id={session['game_id']}")
        assert b"secret-card" not in res.data

    def test_anonymous_transcript_is_forbidden(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.get(f"/transcript?game_id={session['game_id']}&limit=200")
        assert res.status_code == 403
        body = json.loads(res.data)
        assert body.get("status") == "error"

    def test_anonymous_game_status_is_forbidden(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.get(f"/game/status?game_id={session['game_id']}")
        assert res.status_code == 403

    def test_anonymous_eliminate_is_forbidden(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.post(
            "/eliminate_card",
            json={"game_id": session["game_id"], "card_id": 3},
        )
        assert res.status_code == 403

    def test_player1_cannot_eliminate(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.post(
            "/eliminate_card",
            json={
                "game_id": session["game_id"],
                "card_id": 3,
                "participant_id": session["player1_id"],
            },
        )
        assert res.status_code == 403

    def test_player2_can_eliminate(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.post(
            "/eliminate_card",
            json={
                "game_id": session["game_id"],
                "card_id": 3,
                "participant_id": session["player2_id"],
            },
        )
        assert res.status_code == 200
        assert json.loads(res.data).get("status") == "ok"

    def test_bound_participant_can_read_transcript(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.get(
            f"/transcript?game_id={session['game_id']}"
            f"&participant_id={session['player1_id']}&limit=200"
        )
        assert res.status_code == 200
        assert isinstance(json.loads(res.data), list)

    def test_invalid_transcript_limit_is_400(self, client, reset_globals):
        session = self._start_in_progress(client)
        res = client.get(f"/transcript?game_id={session['game_id']}&limit=nope")
        assert res.status_code == 400

    def test_anonymous_ice_servers_is_forbidden(self, client, reset_globals):
        res = client.get("/api/webrtc/ice-servers")
        assert res.status_code == 403

    def test_player_ice_servers_allowed(self, client, reset_globals):
        session = self._start_in_progress(client)
        client.get("/logout")
        res = client.get(
            "/api/webrtc/ice-servers"
            f"?game_id={session['game_id']}&participant_id={session['player1_id']}&role=player1"
        )
        assert res.status_code == 200
        assert json.loads(res.data).get("status") == "ok"
