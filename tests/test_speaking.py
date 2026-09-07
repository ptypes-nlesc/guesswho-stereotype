import json

from app import app, get_db_conn, socketio


class TestSpeakingRelay:
    """Live talker events are ephemeral and staff-only."""

    def test_player_speaking_reaches_moderator_not_other_player(
        self, test_db, reset_globals, create_test_game
    ):
        game_id = "speak-game-1"
        create_test_game(game_id)

        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"

        flask_mod = app.test_client()
        login_res = flask_mod.post(
            "/login",
            data={"password": "test-password", "role": "moderator"},
        )
        assert login_res.status_code == 302
        mod_sock = socketio.test_client(app, flask_test_client=flask_mod)

        p1_sock = socketio.test_client(app, flask_test_client=app.test_client())
        p2_sock = socketio.test_client(app, flask_test_client=app.test_client())
        try:
            mod_ack = mod_sock.emit(
                "join", {"game_id": game_id, "role": "moderator"}, callback=True
            )
            p1_ack = p1_sock.emit(
                "join",
                {
                    "game_id": game_id,
                    "role": "player1",
                    "participant_id": "player-1-uuid",
                },
                callback=True,
            )
            p2_ack = p2_sock.emit(
                "join",
                {
                    "game_id": game_id,
                    "role": "player2",
                    "participant_id": "player-2-uuid",
                },
                callback=True,
            )
            assert mod_ack.get("status") == "ok"
            assert p1_ack.get("status") == "ok"
            assert p2_ack.get("status") == "ok"

            mod_sock.get_received()
            p2_sock.get_received()

            speak_ack = p1_sock.emit(
                "speaking",
                {
                    "game_id": game_id,
                    "role": "player1",
                    "participant_id": "player-1-uuid",
                    "speaking": True,
                },
                callback=True,
            )
            assert speak_ack == {"status": "ok"}

            mod_events = [
                item for item in mod_sock.get_received() if item.get("name") == "speaking"
            ]
            assert len(mod_events) == 1
            payload = mod_events[0]["args"][0]
            assert payload["game_id"] == game_id
            assert payload["role"] == "player1"
            assert payload["speaking"] is True

            p2_events = [
                item for item in p2_sock.get_received() if item.get("name") == "speaking"
            ]
            assert p2_events == []
        finally:
            mod_sock.disconnect()
            p1_sock.disconnect()
            p2_sock.disconnect()

    def test_speaking_is_not_persisted(self, test_db, reset_globals, create_test_game):
        game_id = "speak-game-2"
        create_test_game(game_id)

        app.config["TESTING"] = True
        p1_sock = socketio.test_client(app, flask_test_client=app.test_client())
        try:
            p1_sock.emit(
                "join",
                {
                    "game_id": game_id,
                    "role": "player1",
                    "participant_id": "player-1-uuid",
                },
                callback=True,
            )
            p1_sock.emit(
                "speaking",
                {
                    "game_id": game_id,
                    "role": "player1",
                    "participant_id": "player-1-uuid",
                    "speaking": True,
                },
                callback=True,
            )
        finally:
            p1_sock.disconnect()

        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) AS n FROM events WHERE game_id = %s AND action = %s",
                (game_id, "speaking"),
            )
            assert c.fetchone()["n"] == 0

    def test_moderator_cannot_report_speaking(self, test_db, reset_globals, create_test_game):
        game_id = "speak-game-3"
        create_test_game(game_id)

        app.config["TESTING"] = True
        flask_mod = app.test_client()
        flask_mod.post(
            "/login",
            data={"password": "test-password", "role": "moderator"},
        )
        mod_sock = socketio.test_client(app, flask_test_client=flask_mod)
        try:
            mod_sock.emit("join", {"game_id": game_id, "role": "moderator"}, callback=True)
            ack = mod_sock.emit(
                "speaking",
                {"game_id": game_id, "role": "moderator", "speaking": True},
                callback=True,
            )
            assert ack["status"] == "error"
        finally:
            mod_sock.disconnect()

    def test_auditor_receives_speaking(self, test_db, reset_globals):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"

        flask_mod = app.test_client()
        flask_mod.post(
            "/login",
            data={"password": "test-password", "role": "moderator"},
        )
        open_res = flask_mod.post("/moderator/control/open", json={})
        game_id = json.loads(open_res.data)["game_id"]
        flask_mod.get("/logout")

        flask_aud = app.test_client()
        login_res = flask_aud.post(
            "/login",
            data={"password": "test-auditor-password", "role": "auditor"},
        )
        assert login_res.status_code == 302
        aud_sock = socketio.test_client(app, flask_test_client=flask_aud)
        p1_sock = socketio.test_client(app, flask_test_client=app.test_client())
        try:
            aud_ack = aud_sock.emit(
                "join", {"game_id": game_id, "role": "auditor"}, callback=True
            )
            p1_sock.emit(
                "join",
                {
                    "game_id": game_id,
                    "role": "player1",
                    "participant_id": "player-1-uuid",
                },
                callback=True,
            )
            assert aud_ack.get("status") == "ok", aud_ack
            aud_sock.get_received()

            p1_sock.emit(
                "speaking",
                {
                    "game_id": game_id,
                    "role": "player1",
                    "participant_id": "player-1-uuid",
                    "speaking": True,
                },
                callback=True,
            )
            aud_events = [
                item for item in aud_sock.get_received() if item.get("name") == "speaking"
            ]
            assert len(aud_events) == 1
            assert aud_events[0]["args"][0]["role"] == "player1"
        finally:
            aud_sock.disconnect()
            p1_sock.disconnect()
