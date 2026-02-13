import pytest
import json
import os
import csv
import io
from urllib.parse import urlparse, parse_qs

# Test with the actual MODERATOR_PASSWORD from .env
MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD", "test-password")


class TestGameFlow:
    """Test complete game flow: create, join, ready, start transitions."""
    
    def moderator_login(self, client):
        """Helper to login as moderator and maintain session."""
        with client.session_transaction() as sess:
            sess['moderator'] = True
        return client
    
    @staticmethod
    def extract_tokens_from_csv(csv_response_data):
        """Helper to extract tokens from CSV response."""
        csv_content = csv_response_data.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        tokens = []
        for row in rows[1:]:  # Skip header
            url = row[0]
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            token = query_params.get('token', [None])[0]
            if token:
                tokens.append(token)
        return tokens
    def test_create_game(self, client, reset_globals):
        """Test moderator creating a new game."""
        from app import GAME_STATES
        
        # First login
        self.moderator_login(client)
        
        # Create game
        res = client.post("/moderator/control/open", json={})
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data.get("status") == "ok"
        game_id = data.get("game_id")
        assert game_id is not None
        assert game_id in GAME_STATES
        assert GAME_STATES[game_id]['state'] == 'OPEN'

    def test_generate_tokens(self, client, reset_globals):
        """Test generating access tokens for players."""
        # Create game first
        self.moderator_login(client)
        client.post("/moderator/control/open", json={})
        
        # Generate tokens
        res = client.post("/moderator/tokens/generate", json={"count": 2})
        assert res.status_code == 200
        
        # Parse CSV response
        csv_content = res.data.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        # First row is header, rest are URLs
        assert rows[0] == ['join_url']
        assert len(rows) == 3  # header + 2 tokens
        
        # Extract tokens from URLs
        tokens = []
        for row in rows[1:]:
            url = row[0]
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            token = query_params.get('token', [None])[0]
            assert token is not None
            tokens.append(token)
        
        assert len(tokens) == 2

    def test_player_join_flow(self, client, reset_globals):
        """Test a player joining through token."""
        from app import GAME_STATES
        
        # Create game and generate tokens
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        assert len(tokens) >= 1
        
        # Player enters with token
        res = client.post("/join/enter", json={"token": tokens[0]})
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data.get("status") == "ok"
        participant_id_1 = data.get("participant_id")
        assert participant_id_1 is not None
        
        # Game should still be OPEN with 1 waiting participant
        assert GAME_STATES[game_id]['state'] == 'OPEN'
        assert len(GAME_STATES[game_id]['waiting_participants']) == 1

    def test_game_ready_when_two_players_join(self, client, reset_globals):
        """Test game transitions to READY when 2 players join."""
        from app import GAME_STATES
        
        # Create game and get tokens
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        # Player 1 joins
        res1 = client.post("/join/enter", json={"token": tokens[0]})
        data1 = json.loads(res1.data)
        participant_id_1 = data1.get("participant_id")
        
        # Should still be OPEN
        assert GAME_STATES[game_id]['state'] == 'OPEN'
        
        # Player 2 joins
        res2 = client.post("/join/enter", json={"token": tokens[1]})
        data2 = json.loads(res2.data)
        participant_id_2 = data2.get("participant_id")
        
        # Should now be READY
        assert GAME_STATES[game_id]['state'] == 'READY'
        assert GAME_STATES[game_id]['player1_id'] == participant_id_1
        assert GAME_STATES[game_id]['player2_id'] == participant_id_2

    def test_game_start(self, client, reset_globals):
        """Test moderator starting the game."""
        from app import GAME_STATES
        
        # Setup: create game, get 2 players to join
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        
        # Moderator starts game
        res = client.post("/moderator/control/start", json={})
        assert res.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'IN_PROGRESS'

    def test_player_status_checks(self, client, reset_globals):
        """Test player status endpoints during game flow."""
        # Setup: create game, 2 players, start game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        res1 = client.post("/join/enter", json={"token": tokens[0]})
        p1_id = json.loads(res1.data)['participant_id']
        
        res2 = client.post("/join/enter", json={"token": tokens[1]})
        p2_id = json.loads(res2.data)['participant_id']
        
        # Check status before start (should be 'ready')
        res = client.get(f"/join/status?participant_id={p1_id}")
        data = json.loads(res.data)
        assert data.get("status") == "ready"
        
        # Start game
        client.post("/moderator/control/start", json={})
        
        # Check status after start (should be 'in_game')
        res = client.get(f"/join/status?participant_id={p1_id}")
        data = json.loads(res.data)
        assert data.get("status") == "in_game"
        assert data.get("role") == "player1"
        assert data.get("game_id") == game_id

    def test_moderator_close_entry(self, client, reset_globals):
        """Test moderator closing entry manually before 2 players join."""
        from app import GAME_STATES
        
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        # Verify entry is OPEN
        assert GAME_STATES[game_id]['state'] == 'OPEN'
        
        # Close entry
        res = client.post("/moderator/control/close", json={})
        assert res.status_code == 200
        
        # Verify state transitioned to CLOSED
        assert GAME_STATES[game_id]['state'] == 'CLOSED'

    def test_moderator_end_game(self, client, reset_globals):
        """Test moderator ending a game in progress."""
        from app import GAME_STATES
        
        # Setup: create game, 2 players join, start game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        
        client.post("/moderator/control/start", json={})
        assert GAME_STATES[game_id]['state'] == 'IN_PROGRESS'
        
        # End game
        res = client.post("/moderator/control/end", json={})
        assert res.status_code == 200
        
        # Verify state transitioned to ENDED
        assert GAME_STATES[game_id]['state'] == 'ENDED'

    def test_moderator_reset_session(self, client, reset_globals):
        """Test moderator resetting a completed session."""
        from app import GAME_STATES
        
        # Setup: create game, 2 players join, start, end
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        
        client.post("/moderator/control/start", json={})
        client.post("/moderator/control/end", json={})
        
        assert GAME_STATES[game_id]['state'] == 'ENDED'
        
        # Reset session
        res = client.post("/moderator/control/reset", json={})
        assert res.status_code == 200
        
        # Verify state transitioned to CLOSED
        assert GAME_STATES[game_id]['state'] == 'CLOSED'
        # Verify waiting list and players are cleared
        assert GAME_STATES[game_id]['waiting_participants'] == []
        assert GAME_STATES[game_id]['player1_id'] is None
        assert GAME_STATES[game_id]['player2_id'] is None

    def test_card_elimination_tracking(self, client, reset_globals):
        """Test that eliminated cards are properly tracked in database."""
        from app import get_eliminated_cards
        
        # Setup: create game, start game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        
        client.post("/moderator/control/start", json={})
        
        # Eliminate several cards
        cards_to_eliminate = [1, 3, 5, 7, 11]
        for card_id in cards_to_eliminate:
            res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": card_id})
            assert res.status_code == 200
        
        # Verify all cards are in eliminated list
        eliminated = get_eliminated_cards(game_id)
        for card_id in cards_to_eliminate:
            assert card_id in eliminated
        
        # Verify we have exactly 5 eliminated cards
        assert len(eliminated) == 5

    def test_full_game_lifecycle(self, client, reset_globals):
        """Test complete game lifecycle: open → join → start → eliminate → end → reset."""
        from app import GAME_STATES, get_eliminated_cards
        
        # 1. Moderator opens entry
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        assert res_open.status_code == 200
        game_id = json.loads(res_open.data).get("game_id")
        assert GAME_STATES[game_id]['state'] == 'OPEN'
        
        # 2. Generate tokens
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        assert tokens_res.status_code == 200
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        assert len(tokens) == 2
        
        # 3. Two players join → state should transition to READY
        res1 = client.post("/join/enter", json={"token": tokens[0]})
        assert res1.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'OPEN'  # Still open with 1 player
        
        res2 = client.post("/join/enter", json={"token": tokens[1]})
        assert res2.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'READY'  # Now ready with 2 players
        
        # 4. Moderator starts game
        res_start = client.post("/moderator/control/start", json={})
        assert res_start.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'IN_PROGRESS'
        
        # 5. Players eliminate cards
        eliminated_cards = [2, 4, 6, 8, 10]
        for card_id in eliminated_cards:
            res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": card_id})
            assert res.status_code == 200
        
        # Verify cards are tracked
        eliminated = get_eliminated_cards(game_id)
        assert len(eliminated) == 5
        for card_id in eliminated_cards:
            assert card_id in eliminated
        
        # 6. Moderator ends game
        res_end = client.post("/moderator/control/end", json={})
        assert res_end.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'ENDED'
        
        # 7. Moderator resets session
        res_reset = client.post("/moderator/control/reset", json={})
        assert res_reset.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'CLOSED'
        assert GAME_STATES[game_id]['waiting_participants'] == []
        assert GAME_STATES[game_id]['player1_id'] is None
        assert GAME_STATES[game_id]['player2_id'] is None

    def test_cannot_join_when_entry_closed(self, client, reset_globals):
        """Test that players cannot join when entry is closed."""
        # Setup: Create game and generate tokens
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        # Close entry
        client.post("/moderator/control/close", json={})
        
        # Try to join when entry is closed
        res = client.post("/join/enter", json={"token": tokens[0]})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data.get("status") == "error"
        assert "not open" in data.get("message", "").lower()

    def test_token_reuse_rejected(self, client, reset_globals):
        """Test that the same token cannot be reused after first use."""
        # Setup: Create game and generate tokens
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 1})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        token = tokens[0]
        
        # First use of token should succeed
        res1 = client.post("/join/enter", json={"token": token})
        assert res1.status_code == 200
        
        # Try to reuse same token should fail
        res2 = client.post("/join/enter", json={"token": token})
        assert res2.status_code == 400
        data = json.loads(res2.data)
        assert data.get("status") == "error"
        assert "already been used" in data.get("message", "").lower()

    def test_cannot_start_game_without_players(self, client, reset_globals):
        """Test that game cannot start without 2 players joined."""
        from app import GAME_STATES
        
        # Setup: Create game but no players join
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        # Try to start game when state is OPEN (no players)
        res = client.post("/moderator/control/start", json={})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data.get("status") == "error"
        
        # Verify state is still OPEN, not IN_PROGRESS
        assert GAME_STATES[game_id]['state'] == 'OPEN'

    def test_cannot_start_game_with_one_player(self, client, reset_globals):
        """Test that game cannot start with only 1 player."""
        from app import GAME_STATES
        
        # Setup: Create game and get 1 player to join
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        # Only 1 player joins
        client.post("/join/enter", json={"token": tokens[0]})
        
        # Game should still be OPEN with 1 player
        assert GAME_STATES[game_id]['state'] == 'OPEN'
        
        # Try to start game when state is OPEN (should fail)
        res = client.post("/moderator/control/start", json={})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data.get("status") == "error"
        
        # Verify state is still OPEN
        assert GAME_STATES[game_id]['state'] == 'OPEN'


