import pytest
import json
import os
import csv
import io
from urllib.parse import urlparse, parse_qs

# Test with the actual MODERATOR_PASSWORD from .env
MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD", "test-password")


class TestGamePlay:
    """Test gameplay mechanics like card elimination and game ending."""
    
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
    def test_card_elimination(self, client, reset_globals):
        """Test player 2 eliminating a card."""
        from app import get_eliminated_cards
        
        # Setup: start a game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Eliminate a card
        res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 5})
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data.get("status") == "ok"
        
        # Check card is in eliminated list (returns a set, not list)
        eliminated = get_eliminated_cards(game_id)
        assert 5 in eliminated
        assert isinstance(eliminated, set)

    def test_eliminate_multiple_cards(self, client, reset_globals):
        """Test eliminating multiple cards in sequence."""
        from app import get_eliminated_cards
        
        # Setup: start a game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Eliminate multiple cards
        card_ids = [1, 3, 5, 7]
        for card_id in card_ids:
            res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": card_id})
            assert res.status_code == 200
        
        # Check all cards are eliminated
        eliminated = get_eliminated_cards(game_id)
        for card_id in card_ids:
            assert card_id in eliminated
        
        assert len(eliminated) == len(card_ids)

    def test_eliminate_same_card_twice(self, client, reset_globals):
        """Test eliminating same card twice (should be idempotent)."""
        from app import get_eliminated_cards
        
        # Setup: start a game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Eliminate same card twice
        res1 = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 5})
        res2 = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 5})
        
        assert res1.status_code == 200
        assert res2.status_code == 200  # Should succeed (idempotent)
        
        # Check card is only in set once (sets automatically deduplicate)
        eliminated = get_eliminated_cards(game_id)
        assert 5 in eliminated
        assert len(eliminated) == 1  # Only one card eliminated

    def test_end_game(self, client, reset_globals):
        """Test moderator ending the game."""
        from app import GAME_STATES
        
        # Setup: start a game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # End game
        res = client.post("/moderator/control/end", json={})
        assert res.status_code == 200
        assert GAME_STATES[game_id]['state'] == 'ENDED'

    def test_cannot_eliminate_after_game_ends(self, client, reset_globals):
        """Test that eliminations are still logged even after game ends."""
        from app import get_eliminated_cards
        
        # Setup: start and end a game
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Eliminate during game
        client.post("/eliminate_card", json={"game_id": game_id, "card_id": 3})
        
        # End game
        client.post("/moderator/control/end", json={})
        
        # Try to eliminate after game ends - app allows it (logs are important for research)
        res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 5})
        assert res.status_code == 200  # App continues to accept eliminations for logging
        
        # Both eliminations should be recorded
        eliminated = get_eliminated_cards(game_id)
        assert 3 in eliminated
        assert 5 in eliminated

    def test_eliminate_invalid_card_id(self, client, reset_globals):
        """Test eliminating a card that doesn't exist."""
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Try to eliminate card that doesn't exist (cards are 1-12)
        res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 999})
        # App should still accept it for logging purposes (no validation)
        assert res.status_code == 200

    def test_eliminate_zero_card_id(self, client, reset_globals):
        """Test eliminating card with ID 0 (invalid - falsy value)."""
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Try to eliminate card 0 - app rejects because 0 is falsy
        res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 0})
        assert res.status_code == 400
        data = json.loads(res.data)
        assert data.get("status") == "error"
        assert "card_id" in data.get("message", "").lower()

    def test_eliminate_without_game_id(self, client, reset_globals):
        """Test elimination without providing game_id."""
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        client.post("/moderator/control/start", json={})
        
        # Try to eliminate without game_id (will use DEFAULT_GAME_ID)
        res = client.post("/eliminate_card", json={"card_id": 5})
        assert res.status_code == 200  # Uses default game
        
        # Try without card_id at all
        res = client.post("/eliminate_card", json={"game_id": game_id})
        assert res.status_code == 400  # Should fail - card_id required
        data = json.loads(res.data)
        assert "card_id" in data.get("message", "").lower()

    def test_eliminate_before_game_starts(self, client, reset_globals):
        """Test that cards can be eliminated in READY state (before moderator starts)."""
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        client.post("/join/enter", json={"token": tokens[0]})
        client.post("/join/enter", json={"token": tokens[1]})
        # Don't start game - app should still accept elimination
        
        res = client.post("/eliminate_card", json={"game_id": game_id, "card_id": 5})
        # App accepts eliminations anytime (for flexible research flow)
        assert res.status_code == 200
