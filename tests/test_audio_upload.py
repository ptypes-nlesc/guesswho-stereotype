"""Tests for POST /audio/upload (local-mic stem storage)."""

import csv
import io
import json
import os
from urllib.parse import parse_qs, urlparse

import pytest


class TestAudioUpload:
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
        return game_id, game_state

    def _stem_form(self, game_id, recording_id, role, participant_id=None, **overrides):
        data = {
            "game_id": game_id,
            "recording_id": recording_id,
            "role": role,
            "client_received_ts": "1000",
            "client_recorder_start_ts": "1100",
            "client_recorder_stop_ts": "2100",
            "server_ts": "2026-07-27T12:00:00.000Z",
            "server_stop_ts": "2026-07-27T12:01:00.000Z",
            "mime_type": "audio/webm",
        }
        if participant_id:
            data["participant_id"] = participant_id
        data.update(overrides)
        return data

    def test_upload_requires_timestamps(self, client, reset_globals, tmp_path, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, game_state = self._start_game_in_progress(client)
        p1 = game_state["player1_id"]

        res = client.post(
            "/audio/upload",
            data={
                "game_id": game_id,
                "recording_id": "rec1",
                "role": "player1",
                "participant_id": p1,
            },
            content_type="multipart/form-data",
        )
        assert res.status_code == 400
        body = json.loads(res.data)
        msg = body["message"].lower()
        assert "client_recorder_start_ts" in msg or "required" in msg

    def test_upload_rejects_wrong_participant(self, client, reset_globals, tmp_path, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, _game_state = self._start_game_in_progress(client)

        data = self._stem_form(game_id, "rec1", "player1", participant_id="not-a-player")
        data["file"] = (io.BytesIO(b"fake-webm-bytes"), "stem.webm")
        res = client.post(
            "/audio/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 403

    def test_player_upload_happy_path(self, client, reset_globals, tmp_path, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, game_state = self._start_game_in_progress(client)
        p1 = game_state["player1_id"]
        recording_id = "abcdef0123456789"

        data = self._stem_form(game_id, recording_id, "player1", participant_id=p1)
        data["file"] = (io.BytesIO(b"fake-webm-bytes-player1"), "stem.webm")
        res = client.post(
            "/audio/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 200, res.data
        body = json.loads(res.data)
        assert body["status"] == "ok"
        assert body["recording_id"] == recording_id
        assert body["role"] == "player1"
        assert body["byte_size"] == len(b"fake-webm-bytes-player1")
        assert body["audio_path"].endswith(f"{recording_id}_player1_{p1}.webm")

        abs_path = os.path.join(tmp_path, body["audio_path"])
        assert os.path.isfile(abs_path)
        with open(abs_path, "rb") as fh:
            assert fh.read() == b"fake-webm-bytes-player1"

        with app_module.get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT recording_id, role, participant_id, byte_size, audio_path,
                       client_recorder_start_ts, client_recorder_stop_ts
                FROM audio_events
                WHERE game_id = %s AND recording_id = %s AND role = %s
                """,
                (game_id, recording_id, "player1"),
            )
            row = c.fetchone()
            assert row is not None
            assert row["participant_id"] == p1
            assert row["byte_size"] == len(b"fake-webm-bytes-player1")
            assert row["client_recorder_start_ts"] == 1100
            assert row["client_recorder_stop_ts"] == 2100

        # Checklist appears on moderator status
        status = json.loads(client.get("/moderator/control/status").data)
        assert status["last_audio_uploads"]["recording_id"] == recording_id
        assert status["last_audio_uploads"]["stems"]["player1"]["status"] == "ok"

    def test_upload_is_idempotent(self, client, reset_globals, tmp_path, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, game_state = self._start_game_in_progress(client)
        p1 = game_state["player1_id"]
        recording_id = "rec-idempotent"

        data = self._stem_form(game_id, recording_id, "player1", participant_id=p1)
        data["file"] = (io.BytesIO(b"first"), "stem.webm")
        res1 = client.post("/audio/upload", data=data, content_type="multipart/form-data")
        assert res1.status_code == 200

        data2 = self._stem_form(game_id, recording_id, "player1", participant_id=p1)
        data2["file"] = (io.BytesIO(b"second-overwrite"), "stem.webm")
        res2 = client.post("/audio/upload", data=data2, content_type="multipart/form-data")
        assert res2.status_code == 200
        body = json.loads(res2.data)
        abs_path = os.path.join(tmp_path, body["audio_path"])
        with open(abs_path, "rb") as fh:
            assert fh.read() == b"second-overwrite"

        with app_module.get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) AS n FROM audio_events WHERE game_id=%s AND recording_id=%s AND role=%s",
                (game_id, recording_id, "player1"),
            )
            assert c.fetchone()["n"] == 1

    def test_moderator_upload_requires_staff_session(
        self, client, reset_globals, tmp_path, monkeypatch
    ):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, _game_state = self._start_game_in_progress(client)

        # Clear moderator session
        with client.session_transaction() as sess:
            sess.clear()

        data = self._stem_form(game_id, "rec-mod", "moderator")
        data["file"] = (io.BytesIO(b"mod-bytes"), "mod.webm")
        res = client.post("/audio/upload", data=data, content_type="multipart/form-data")
        assert res.status_code == 403

    def test_moderator_upload_happy_path(self, client, reset_globals, tmp_path, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, _game_state = self._start_game_in_progress(client)
        recording_id = "rec-mod-ok"

        data = self._stem_form(game_id, recording_id, "moderator")
        data["file"] = (io.BytesIO(b"moderator-audio"), "mod.webm")
        res = client.post("/audio/upload", data=data, content_type="multipart/form-data")
        assert res.status_code == 200, res.data
        body = json.loads(res.data)
        assert "moderator" in body["audio_path"]
        assert os.path.isfile(os.path.join(tmp_path, body["audio_path"]))

    def test_upload_after_role_swap_still_accepts_participant(
        self, client, reset_globals, tmp_path, monkeypatch
    ):
        """Late upload after swap: participant is still in the game; role label is trusted."""
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, game_state = self._start_game_in_progress(client)
        original_p1 = game_state["player1_id"]

        client.post("/moderator/control/swap_roles", json={})
        game_state = app_module.get_game_state(game_id)
        assert game_state["player1_id"] != original_p1
        assert original_p1 == game_state["player2_id"]

        data = self._stem_form(
            game_id, "rec-pre-swap", "player1", participant_id=original_p1
        )
        data["file"] = (io.BytesIO(b"late-stem"), "stem.webm")
        res = client.post("/audio/upload", data=data, content_type="multipart/form-data")
        assert res.status_code == 200, res.data

    def test_upload_emits_socket_event(
        self, client, socketio_client, reset_globals, tmp_path, monkeypatch
    ):
        import app as app_module

        monkeypatch.setattr(app_module, "AUDIO_STORAGE_DIR", str(tmp_path))
        game_id, game_state = self._start_game_in_progress(client)
        p1 = game_state["player1_id"]

        socketio_client.emit(
            "join",
            {"game_id": game_id, "role": "player1", "participant_id": p1},
        )
        socketio_client.get_received()

        data = self._stem_form(game_id, "rec-sock", "player1", participant_id=p1)
        data["file"] = (io.BytesIO(b"sock-bytes"), "stem.webm")
        res = client.post("/audio/upload", data=data, content_type="multipart/form-data")
        assert res.status_code == 200

        received = socketio_client.get_received()
        events = [item for item in received if item.get("name") == "audio_upload_complete"]
        assert len(events) == 1
        payload = events[0]["args"][0]
        assert payload["game_id"] == game_id
        assert payload["role"] == "player1"
        assert payload["recording_id"] == "rec-sock"
