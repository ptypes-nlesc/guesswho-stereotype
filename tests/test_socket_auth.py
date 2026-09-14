"""Socket.IO events require a DB role binding or a staff session."""

from app import CHAT_MAX_LENGTH, _socketio_cors_origins


class TestSocketAuth:
    def test_join_without_participant_id_is_rejected(
        self, socketio_client, reset_globals, create_test_game
    ):
        game_id = "sock-auth-missing"
        create_test_game(game_id)
        ack = socketio_client.emit(
            "join",
            {"game_id": game_id, "role": "player1"},
            callback=True,
        )
        assert ack.get("status") == "error"
        assert "participant_id" in ack.get("message", "").lower()

    def test_join_unbound_participant_is_rejected(
        self, socketio_client, reset_globals, create_test_game
    ):
        game_id = "sock-auth-unbound"
        create_test_game(game_id)
        ack = socketio_client.emit(
            "join",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "stranger",
            },
            callback=True,
        )
        assert ack.get("status") == "error"

    def test_join_does_not_create_binding_from_claimed_role(
        self, socketio_client, reset_globals, create_test_game
    ):
        from app import get_participant_binding

        game_id = "sock-auth-no-upsert"
        create_test_game(game_id, bind_default_players=False)
        ack = socketio_client.emit(
            "join",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "invented-id",
            },
            callback=True,
        )
        assert ack.get("status") == "error"
        assert get_participant_binding(game_id, "invented-id") is None

    def test_chat_without_binding_is_rejected(
        self, socketio_client, reset_globals, create_test_game
    ):
        from app import get_chat_history

        game_id = "sock-auth-chat"
        create_test_game(game_id, bind_default_players=False)
        ack = socketio_client.emit(
            "chat",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "invented-id",
                "text": "hello",
            },
            callback=True,
        )
        assert ack.get("status") == "error"
        assert get_chat_history(game_id) == []

    def test_bound_player_can_chat(
        self, socketio_client, reset_globals, create_test_game
    ):
        from app import get_chat_history

        game_id = "sock-auth-ok"
        create_test_game(game_id)
        join_ack = socketio_client.emit(
            "join",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "player-1-uuid",
            },
            callback=True,
        )
        chat_ack = socketio_client.emit(
            "chat",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "player-1-uuid",
                "text": "ok",
            },
            callback=True,
        )
        assert join_ack.get("status") == "ok"
        assert chat_ack.get("status") == "ok"
        assert get_chat_history(game_id)[0]["text"] == "ok"

    def test_chat_text_is_capped(self, socketio_client, reset_globals, create_test_game):
        from app import get_chat_history

        game_id = "sock-auth-long"
        create_test_game(game_id)
        socketio_client.emit(
            "join",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "player-1-uuid",
            },
            callback=True,
        )
        ack = socketio_client.emit(
            "chat",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "player-1-uuid",
                "text": "x" * (CHAT_MAX_LENGTH + 1),
            },
            callback=True,
        )
        assert ack.get("status") == "error"
        assert "too long" in ack.get("message", "").lower()
        assert get_chat_history(game_id) == []

    def test_speaking_requires_binding(
        self, socketio_client, reset_globals, create_test_game
    ):
        game_id = "sock-auth-speak"
        create_test_game(game_id, bind_default_players=False)
        ack = socketio_client.emit(
            "speaking",
            {
                "game_id": game_id,
                "role": "player1",
                "participant_id": "invented-id",
                "speaking": True,
            },
            callback=True,
        )
        assert ack.get("status") == "error"

    def test_moderator_join_without_session_is_rejected(
        self, socketio_client, reset_globals, create_test_game
    ):
        game_id = "sock-auth-mod"
        create_test_game(game_id)
        ack = socketio_client.emit(
            "join",
            {"game_id": game_id, "role": "moderator"},
            callback=True,
        )
        assert ack.get("status") == "error"

    def test_cors_origins_include_loopback_in_tests(self):
        origins = _socketio_cors_origins()
        assert "http://127.0.0.1:5000" in origins
        assert "*" not in origins
