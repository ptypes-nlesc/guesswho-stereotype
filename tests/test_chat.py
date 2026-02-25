import pytest
import json
import os
import csv
import io
import uuid
from urllib.parse import urlparse, parse_qs

# Test with the actual MODERATOR_PASSWORD from .env
MODERATOR_PASSWORD = os.getenv("MODERATOR_PASSWORD", "test-password")


class TestChat:
    """Test 3-way chat between Player 1, Player 2, and Moderator."""
    
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
    
    def setup_game_with_players(self, client):
        """Helper to setup a game with 2 players and moderator logged in."""
        self.moderator_login(client)
        res_open = client.post("/moderator/control/open", json={})
        game_id = json.loads(res_open.data).get("game_id")
        
        tokens_res = client.post("/moderator/tokens/generate", json={"count": 2})
        tokens = self.extract_tokens_from_csv(tokens_res.data)
        
        res1 = client.post("/join/enter", json={"token": tokens[0]})
        participant1_id = json.loads(res1.data).get("participant_id")
        
        res2 = client.post("/join/enter", json={"token": tokens[1]})
        participant2_id = json.loads(res2.data).get("participant_id")
        
        # Game automatically transitions to READY when 2 players join
        # Now start the game
        client.post("/moderator/control/start", json={})
        
        return {
            'game_id': game_id,
            'player1_id': participant1_id,
            'player2_id': participant2_id
        }

    def test_player1_send_chat(self, socketio_client, reset_globals, create_test_game):
        """Test Player 1 sending a chat message."""
        from app import get_transcript
        
        game_id = "test-game-123"
        player1_id = "player-1-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        # Emit join event
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        # Emit chat message
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': 'Is it a person?'
        })
        
        # Check that message was logged to database
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat' and e['role'] == 'player1']
        assert len(chat_events) > 0
        assert chat_events[0]['text'] == 'Is it a person?'

    def test_player2_send_chat(self, socketio_client, reset_globals, create_test_game):
        """Test Player 2 sending a chat message."""
        from app import get_transcript
        
        game_id = "test-game-456"
        player2_id = "player-2-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        # Emit join event
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id
        })
        
        # Emit chat message
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id,
            'text': 'The person has brown hair.'
        })
        
        # Check that message was logged
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat' and e['role'] == 'player2']
        assert len(chat_events) > 0
        assert chat_events[0]['text'] == 'The person has brown hair.'

    def test_moderator_send_chat(self, socketio_client, reset_globals, create_test_game):
        """Test Moderator sending a chat message."""
        from app import get_transcript
        
        game_id = "test-game-789"
        moderator_id = "moderator-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        # Emit join event
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'moderator',
            'participant_id': moderator_id
        })
        
        # Emit chat message
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'moderator',
            'participant_id': moderator_id,
            'text': 'Good question. Please continue.'
        })
        
        # Check that message was logged
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat' and e['role'] == 'moderator']
        assert len(chat_events) > 0
        assert chat_events[0]['text'] == 'Good question. Please continue.'

    def test_chat_message_missing_text(self, socketio_client, reset_globals, create_test_game):
        """Test sending chat without text field."""
        game_id = "test-game-empty"
        player1_id = "player-1-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        # Send chat without text
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': None
        })
        
        # Empty text should still be logged (for research purposes)
        from app import get_transcript
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat']
        assert len(chat_events) > 0

    def test_chat_without_game_id(self, socketio_client, reset_globals, create_test_game):
        """Test chat without game_id returns error."""
        player1_id = "player-1-uuid"
        
        # Send chat without game_id (should return error)
        result = socketio_client.emit('chat', {
            'role': 'player1',
            'participant_id': player1_id,
            'text': 'Message without game_id'
        }, callback=True)
        
        # Should return error response
        if result:
            assert result.get('status') == 'error'
            assert 'game_id' in result.get('message', '').lower()

    def test_chat_event_logging_complete(self, socketio_client, reset_globals, create_test_game):
        """Test that chat events are fully logged with all metadata."""
        from app import get_transcript
        
        game_id = "test-game-metadata"
        player1_id = "player-1-uuid"
        message_text = "Does it have green eyes?"
        
        # Create game record in database first
        create_test_game(game_id)
        
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': message_text
        })
        
        # Verify complete event logging
        transcript = get_transcript(game_id)
        chat_event = [e for e in transcript if e['action'] == 'chat'][0]
        
        assert chat_event['role'] == 'player1'
        assert chat_event['action'] == 'chat'
        assert chat_event['text'] == message_text
        assert chat_event['participant_id'] == player1_id
        assert chat_event['game_id'] == game_id
        assert chat_event['timestamp'] is not None

    def test_multiple_chat_sequence(self, socketio_client, reset_globals, create_test_game):
        """Test a sequence of chat messages (Q&A flow)."""
        from app import get_transcript
        
        game_id = "test-game-sequence"
        player1_id = "player-1-uuid"
        player2_id = "player-2-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        # Both join
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id
        })
        
        # Player 2 asks
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id,
            'text': 'Is it wearing a hat?'
        })
        
        # Player 1 answers
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': 'Yes.'
        })
        
        # Player 2 clarifies
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id,
            'text': 'Is it a red hat?'
        })
        
        # Check sequence
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat']
        
        assert len(chat_events) == 3
        assert chat_events[0]['role'] == 'player2'
        assert chat_events[0]['text'] == 'Is it wearing a hat?'
        assert chat_events[1]['role'] == 'player1'
        assert chat_events[1]['text'] == 'Yes.'
        assert chat_events[2]['role'] == 'player2'
        assert chat_events[2]['text'] == 'Is it a red hat?'

    def test_chat_with_special_characters(self, socketio_client, reset_globals, create_test_game):
        """Test chat messages with special characters and unicode."""
        from app import get_transcript
        
        game_id = "test-game-special"
        player1_id = "player-1-uuid"
        special_text = "Does it have café? 🎓 <script>alert('xss')</script>"
        
        # Create game record in database first
        create_test_game(game_id)
        
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': special_text
        })
        
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat']
        assert len(chat_events) > 0
        assert chat_events[0]['text'] == special_text

    def test_chat_before_game_starts(self, socketio_client, reset_globals, create_test_game):
        """Test that chat can happen before game officially starts."""
        from app import get_transcript
        
        game_id = "test-game-early-chat"
        player1_id = "player-1-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        # Send chat while in READY state (before moderator starts)
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': 'Ready when you are'
        })
        
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat']
        assert len(chat_events) > 0

    def test_chat_after_game_ends(self, socketio_client, reset_globals, create_test_game):
        """Test that chat can continue after game ends (for debrief)."""
        from app import get_transcript
        
        game_id = "test-game-debrief"
        player1_id = "player-1-uuid"
        
        # Create game record in database first
        create_test_game(game_id)
        
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })
        
        # Send chat after game logically "ends"
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': 'That was interesting!'
        })
        
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat']
        assert len(chat_events) > 0

    def test_multiple_chat_sequence(self, socketio_client, reset_globals, create_test_game):
        """Test a sequence of chat messages (Q&A flow)."""
        from app import get_transcript

        game_id = str(uuid.uuid4())
        player1_id = "player-1-uuid"
        player2_id = "player-2-uuid"
        
        # Create game record in database first
        create_test_game(game_id)

        # Both join
        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id
        })

        socketio_client.emit('join', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id
        })

        # Player 2 asks
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id,
            'text': 'Is it wearing a hat?'
        })

        # Player 1 answers
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player1',
            'participant_id': player1_id,
            'text': 'Yes.'
        })

        # Player 2 clarifies
        socketio_client.emit('chat', {
            'game_id': game_id,
            'role': 'player2',
            'participant_id': player2_id,
            'text': 'Is it a red hat?'
        })

        # Check sequence
        transcript = get_transcript(game_id)
        chat_events = [e for e in transcript if e['action'] == 'chat']

        assert len(chat_events) == 3
        assert chat_events[0]['role'] == 'player2'
        assert chat_events[0]['text'] == 'Is it wearing a hat?'
        assert chat_events[1]['role'] == 'player1'
        assert chat_events[1]['text'] == 'Yes.'
        assert chat_events[2]['role'] == 'player2'
        assert chat_events[2]['text'] == 'Is it a red hat?'
