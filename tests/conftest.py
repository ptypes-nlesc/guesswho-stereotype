import os
import pytest
import pymysql

# Set TESTING flag before importing app
os.environ['TESTING'] = '1'

# Load .env if it exists (local development)
from dotenv import load_dotenv
load_dotenv()

# Set CI defaults for MySQL if not already set by .env
os.environ.setdefault('MYSQL_HOST', 'localhost')
os.environ.setdefault('MYSQL_PORT', '3306')
os.environ.setdefault('MYSQL_USER', 'exposed_user')
os.environ.setdefault('MYSQL_PASSWORD', 'exposed_pass')
os.environ.setdefault('MYSQL_DATABASE', 'exposeddb')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('MODERATOR_PASSWORD', 'test-password')

from app import app, socketio, init_db

@pytest.fixture(autouse=True)
def ensure_test_password():
    """Ensure MODERATOR_PASSWORD is set to test value for all tests."""
    import app as app_module
    app_module.MODERATOR_PASSWORD = "test-password"
    yield
    # Restore after test (optional, but good practice)

@pytest.fixture(scope='function')
def test_db():
    """Setup test database - shared by all fixtures."""
    import app as app_module
    original_mysql_config = dict(app_module.MYSQL_CONFIG)
    
    # Use test database name
    app_module.MYSQL_CONFIG['database'] = 'exposeddb_test'
    
    admin_user = os.getenv('MYSQL_ROOT_USER', 'root')
    admin_password = os.getenv('MYSQL_ROOT_PASSWORD')
    admin_conn_user = None

    # Create test database using admin credentials (required for CREATE/DROP)
    try:
        admin_conn = pymysql.connect(
            host=original_mysql_config['host'],
            port=original_mysql_config['port'],
            user=admin_user,
            password=admin_password,
            charset='utf8mb4'
        )
        admin_conn_user = admin_user
    except pymysql.err.OperationalError as exc:
        admin_conn = None
        fallback_error = exc

    if admin_conn is None:
        try:
            admin_conn = pymysql.connect(
                host=original_mysql_config['host'],
                port=original_mysql_config['port'],
                user=original_mysql_config['user'],
                password=original_mysql_config['password'],
                charset='utf8mb4'
            )
            admin_conn_user = original_mysql_config['user']
        except pymysql.err.OperationalError as exc:
            raise RuntimeError(
                "Test DB setup failed. Set MYSQL_ROOT_PASSWORD (and optional MYSQL_ROOT_USER) "
                "so tests can create/drop the test database."
            ) from exc

    cursor = admin_conn.cursor()
    cursor.execute("DROP DATABASE IF EXISTS exposeddb_test")
    cursor.execute("CREATE DATABASE exposeddb_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

    if admin_conn_user != original_mysql_config['user']:
        # Grant permissions to app user on test database
        cursor.execute(
            "GRANT ALL PRIVILEGES ON exposeddb_test.* TO %s@'%%'",
            (original_mysql_config['user'],)
        )
        cursor.execute("FLUSH PRIVILEGES")

    admin_conn.commit()
    cursor.close()
    admin_conn.close()
    
    # Initialize test database tables
    with app.app_context():
        init_db()
    
    yield
    
    # Cleanup: drop test database using admin credentials, fallback to app user
    admin_user = os.getenv('MYSQL_ROOT_USER', 'root')
    admin_password = os.getenv('MYSQL_ROOT_PASSWORD')
    try:
        admin_conn = pymysql.connect(
            host=original_mysql_config['host'],
            port=original_mysql_config['port'],
            user=admin_user,
            password=admin_password,
            charset='utf8mb4'
        )
    except pymysql.err.OperationalError:
        admin_conn = pymysql.connect(
            host=original_mysql_config['host'],
            port=original_mysql_config['port'],
            user=original_mysql_config['user'],
            password=original_mysql_config['password'],
            charset='utf8mb4'
        )

    cursor = admin_conn.cursor()
    cursor.execute("DROP DATABASE IF EXISTS exposeddb_test")
    admin_conn.commit()
    cursor.close()
    admin_conn.close()
    
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
    """Reset Redis and in-memory state between tests."""
    import app as app_module
    
    # Store originals for in-memory fallback
    original_game_states = dict(app_module.GAME_STATES)
    original_session_game_id = app_module.CURRENT_SESSION_GAME_ID
    original_participant_roles = dict(app_module.PARTICIPANT_ROLES)
    original_voice_participants = dict(app_module.VOICE_PARTICIPANTS)
    
    yield
    
    # Reset Redis state if Redis is available
    if app_module.get_redis():
        try:
            redis_client = app_module.get_redis()
            # Clear all game state keys
            for key in redis_client.keys("game:*:state"):
                redis_client.delete(key)
            # Clear all role keys
            for key in redis_client.keys("roles:*"):
                redis_client.delete(key)
            # Clear all voice keys
            for key in redis_client.keys("voice:*"):
                redis_client.delete(key)
            # Clear current session
            redis_client.delete("current_session_game_id")
        except Exception as e:
            print(f"Warning: Could not reset Redis: {e}")
    
    # Reset in-memory fallback dicts
    app_module.GAME_STATES.clear()
    app_module.GAME_STATES.update(original_game_states)
    app_module.CURRENT_SESSION_GAME_ID = original_session_game_id
    app_module.PARTICIPANT_ROLES.clear()
    app_module.PARTICIPANT_ROLES.update(original_participant_roles)
    app_module.VOICE_PARTICIPANTS.clear()
    app_module.VOICE_PARTICIPANTS.update(original_voice_participants)

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