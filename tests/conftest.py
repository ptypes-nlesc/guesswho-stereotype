import os
import pytest
import pymysql

# Set TESTING flag before importing app
os.environ['TESTING'] = '1'

from app import app, socketio, init_db

@pytest.fixture(autouse=True)
def override_password(monkeypatch):
    """Auto-use fixture: sets MODERATOR_PASSWORD for all tests."""
    monkeypatch.setenv("MODERATOR_PASSWORD", "test-password")
    
    # Reload MODERATOR_PASSWORD in app module since it's already imported
    import app as app_module
    app_module.MODERATOR_PASSWORD = "test-password"

@pytest.fixture(scope='function')
def test_db():
    """Setup test database - shared by all fixtures."""
    import app as app_module
    original_mysql_config = dict(app_module.MYSQL_CONFIG)
    
    # Use test database name
    app_module.MYSQL_CONFIG['database'] = 'exposeddb_test'
    
    # Create test database
    conn = pymysql.connect(
        host=original_mysql_config['host'],
        port=original_mysql_config['port'],
        user=original_mysql_config['user'],
        password=original_mysql_config['password'],
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    cursor.execute("DROP DATABASE IF EXISTS exposeddb_test")
    cursor.execute("CREATE DATABASE exposeddb_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit()
    cursor.close()
    conn.close()
    
    # Initialize test database tables
    with app.app_context():
        init_db()
    
    yield
    
    # Cleanup: drop test database and restore config
    conn = pymysql.connect(
        host=original_mysql_config['host'],
        port=original_mysql_config['port'],
        user=original_mysql_config['user'],
        password=original_mysql_config['password'],
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    cursor.execute("DROP DATABASE IF EXISTS exposeddb_test")
    conn.commit()
    cursor.close()
    conn.close()
    
    app_module.MYSQL_CONFIG.update(original_mysql_config)

@pytest.fixture
def client(test_db):
    """Create Flask test client with test MySQL database."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.test_client() as client:
        yield client

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
def socketio_client(test_db):
    """Create Flask-SocketIO test client with test MySQL database."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    client = socketio.test_client(app, flask_test_client=app.test_client())
    yield client
    client.disconnect()

@pytest.fixture
def create_test_game():
    """Helper to create a game record in the database for testing."""
    import app as app_module
    import pymysql
    
    def _create_game(game_id, chosen_card=None):
        """Insert a game record into the games table."""
        with app_module.get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO games (id, chosen_card, created_at) VALUES (%s, %s, NOW())",
                (game_id, chosen_card)
            )
        return game_id
    
    return _create_game