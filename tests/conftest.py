import os
import tempfile
import sqlite3
import pytest
from app import app, socketio, init_db, get_db_conn

@pytest.fixture(autouse=True)
def override_password(monkeypatch):
    """Auto-use fixture: sets MODERATOR_PASSWORD for all tests."""
    monkeypatch.setenv("MODERATOR_PASSWORD", "test-password")
    
    # Reload MODERATOR_PASSWORD in app module since it's already imported
    import app as app_module
    app_module.MODERATOR_PASSWORD = "test-password"

@pytest.fixture
def client():
    """Create Flask test client with in-memory SQLite database."""
    # Use temporary file for SQLite during tests
    db_fd, db_path = tempfile.mkstemp()
    
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    # Override DB_PATH to use temp file
    import app as app_module
    original_db_path = app_module.DB_PATH
    app_module.DB_PATH = db_path
    
    # Initialize database
    with app.app_context():
        init_db()
    
    with app.test_client() as client:
        yield client
    
    # Cleanup
    app_module.DB_PATH = original_db_path
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def reset_globals():
    """Reset in-memory state between tests."""
    import app as app_module
    
    # Store originals - only for variables that exist
    original_game_states = dict(app_module.GAME_STATES)
    original_session_game_id = app_module.CURRENT_SESSION_GAME_ID
    original_participant_roles = dict(app_module.PARTICIPANT_ROLES)
    original_voice_participants = dict(app_module.VOICE_PARTICIPANTS)
    
    # Only store if these exist
    original_voice_choices = dict(getattr(app_module, 'TOKEN_VOICE_CHOICES', {}))
    
    yield
    
    # Reset after test
    app_module.GAME_STATES.clear()
    app_module.GAME_STATES.update(original_game_states)
    app_module.CURRENT_SESSION_GAME_ID = original_session_game_id
    app_module.PARTICIPANT_ROLES.clear()
    app_module.PARTICIPANT_ROLES.update(original_participant_roles)
    app_module.VOICE_PARTICIPANTS.clear()
    app_module.VOICE_PARTICIPANTS.update(original_voice_participants)
    
    # Reset if exists
    if hasattr(app_module, 'TOKEN_VOICE_CHOICES'):
        app_module.TOKEN_VOICE_CHOICES.clear()
        app_module.TOKEN_VOICE_CHOICES.update(original_voice_choices)

@pytest.fixture
def socketio_client():
    """Create Flask-SocketIO test client."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    client = socketio.test_client(app, flask_test_client=app.test_client())
    yield client
    client.disconnect()