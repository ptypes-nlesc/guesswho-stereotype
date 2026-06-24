import csv
import io
import json
from urllib.parse import parse_qs, urlparse


class TestRecordingControl:
    """Test moderator recording start/stop controls and socket broadcasts."""

    def moderator_login(self, client):
        with client.session_transaction() as sess:
            sess["moderator"] = True
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

    def _start_game_in_progress(self, client):
        from app import get_game_state

        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")

        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})

        game_state = get_game_state(game_id)
        assert game_state["state"] == "IN_PROGRESS"
        return game_id

    def test_recording_start_requires_auth(self, client, reset_globals):
        res = client.post("/moderator/control/recording/start", json={})
        assert res.status_code == 403

    def test_recording_stop_requires_auth(self, client, reset_globals):
        res = client.post("/moderator/control/recording/stop", json={})
        assert res.status_code == 403

    def test_recording_start_requires_in_progress(self, client, reset_globals):
        self.moderator_login(client)
        client.post("/moderator/control/open", json={})

        res = client.post("/moderator/control/recording/start", json={})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data["status"] == "error"

    def test_recording_start_and_stop_updates_state(self, client, reset_globals):
        from app import get_game_state

        game_id = self._start_game_in_progress(client)

        res_start = client.post("/moderator/control/recording/start", json={})
        assert res_start.status_code == 200
        start_data = json.loads(res_start.data)
        assert start_data["status"] == "ok"
        assert start_data["recording_id"]
        assert start_data["server_ts"].endswith("Z")

        game_state = get_game_state(game_id)
        assert game_state["recording_active"] is True
        assert game_state["recording_id"] == start_data["recording_id"]

        res_stop = client.post("/moderator/control/recording/stop", json={})
        assert res_stop.status_code == 200
        stop_data = json.loads(res_stop.data)
        assert stop_data["status"] == "ok"
        assert stop_data["recording_id"] == start_data["recording_id"]

        game_state = get_game_state(game_id)
        assert game_state["recording_active"] is False

    def test_recording_start_rejects_duplicate(self, client, reset_globals):
        self._start_game_in_progress(client)
        client.post("/moderator/control/recording/start", json={})

        res = client.post("/moderator/control/recording/start", json={})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert "already active" in data["message"].lower()

    def test_recording_stop_is_idempotent(self, client, reset_globals):
        self._start_game_in_progress(client)

        res = client.post("/moderator/control/recording/stop", json={})
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "ok"
        assert data.get("message") == "No active recording"

    def test_recording_status_in_control_status(self, client, reset_globals):
        self._start_game_in_progress(client)
        client.post("/moderator/control/recording/start", json={})

        res = client.get("/moderator/control/status")
        data = json.loads(res.data)
        assert data["status"] == "ok"
        assert data["recording_active"] is True
        assert data["recording_id"]

    def test_recording_start_emits_socket_event(
        self, client, socketio_client, reset_globals
    ):
        game_id = self._start_game_in_progress(client)

        socketio_client.emit(
            "join",
            {"game_id": game_id, "role": "player1", "participant_id": "test-participant"},
        )
        socketio_client.get_received()

        res = client.post("/moderator/control/recording/start", json={})
        assert res.status_code == 200
        start_data = json.loads(res.data)

        received = socketio_client.get_received()
        recording_events = [
            item
            for item in received
            if item.get("name") == "recording_start"
        ]
        assert len(recording_events) == 1
        payload = recording_events[0]["args"][0]
        assert payload["game_id"] == game_id
        assert payload["recording_id"] == start_data["recording_id"]
        assert payload["server_ts"].endswith("Z")

    def test_end_game_emits_game_ended_socket(
        self, client, socketio_client, reset_globals
    ):
        game_id = self._start_game_in_progress(client)

        socketio_client.emit(
            "join",
            {"game_id": game_id, "role": "player1", "participant_id": "test-participant"},
        )
        socketio_client.get_received()

        client.post("/moderator/control/end", json={})

        received = socketio_client.get_received()
        ended_events = [item for item in received if item.get("name") == "game_ended"]
        assert len(ended_events) == 1
        payload = ended_events[0]["args"][0]
        assert payload["game_id"] == game_id
        assert payload["state"] == "ENDED"

    def test_end_game_stops_active_recording(self, client, reset_globals):
        from app import get_game_state

        game_id = self._start_game_in_progress(client)
        client.post("/moderator/control/recording/start", json={})

        client.post("/moderator/control/end", json={})

        game_state = get_game_state(game_id)
        assert game_state["state"] == "ENDED"
        assert game_state["recording_active"] is False