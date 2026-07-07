import os
import pytest
import pymysql

# Set TESTING flag before importing app
os.environ['TESTING'] = '1'

# Load .env if it exists (local development)
from dotenv import load_dotenv
load_dotenv()

# Set CI defaults for DB config if not already set by .env
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '3306')
os.environ.setdefault('DB_USER', 'xposed_user')
os.environ.setdefault('DB_PWD', 'xposed_pass')
os.environ.setdefault('DB_NAME', 'xposed_db')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('MODERATOR_PASSWORD', 'test-password')
os.environ.setdefault('AUDITOR_PASSWORD', 'test-auditor-password')

from app import app, socketio, init_db

@pytest.fixture(autouse=True)
def ensure_test_password():
    """Ensure MODERATOR_PASSWORD is set to test value for all tests."""
    import app as app_module
    app_module.MODERATOR_PASSWORD = "test-password"
    app_module.AUDITOR_PASSWORD = "test-auditor-password"
    yield
    # Restore after test (optional, but good practice)

@pytest.fixture(scope='function')
def test_db():
    """Setup test database - shared by all fixtures."""
    import app as app_module
    original_db_config = dict(app_module.DB_CONFIG)
    test_database = 'xposed_db_test'
    
    # Use test database name
    app_module.DB_CONFIG['database'] = test_database
    
    admin_user = os.getenv('DB_ROOT_USER', 'root')
    admin_password = os.getenv('DB_ROOT_PASSWORD')
    admin_conn_user = None

    # Create test database using admin credentials (required for CREATE/DROP)
    try:
        admin_conn = pymysql.connect(
            host=original_db_config['host'],
            port=original_db_config['port'],
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
                host=original_db_config['host'],
                port=original_db_config['port'],
                user=original_db_config['user'],
                password=original_db_config['password'],
                charset='utf8mb4'
            )
            admin_conn_user = original_db_config['user']
        except pymysql.err.OperationalError as exc:
            raise RuntimeError(
                "Test DB setup failed. Set DB_ROOT_PASSWORD (and optional DB_ROOT_USER) "
                "so tests can create/drop the test database."
            ) from exc

    cursor = admin_conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS {test_database}")
    cursor.execute(f"CREATE DATABASE {test_database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

    if admin_conn_user != original_db_config['user']:
        # Grant permissions to app user on test database
        cursor.execute(
            f"GRANT ALL PRIVILEGES ON {test_database}.* TO %s@'%%'",
            (original_db_config['user'],)
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
    admin_user = os.getenv('DB_ROOT_USER', 'root')
    admin_password = os.getenv('DB_ROOT_PASSWORD')
    try:
        admin_conn = pymysql.connect(
            host=original_db_config['host'],
            port=original_db_config['port'],
            user=admin_user,
            password=admin_password,
            charset='utf8mb4'
        )
    except pymysql.err.OperationalError:
        admin_conn = pymysql.connect(
            host=original_db_config['host'],
            port=original_db_config['port'],
            user=original_db_config['user'],
            password=original_db_config['password'],
            charset='utf8mb4'
        )

    cursor = admin_conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS {test_database}")
    admin_conn.commit()
    cursor.close()
    admin_conn.close()
    
    app_module.DB_CONFIG.update(original_db_config)

@pytest.fixture
def client(test_db):
    """Create Flask test client with test MySQL database."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.test_client() as client:
        yield client

def _reset_app_globals(app_module):
    """Clear Redis and in-memory runtime state."""
    if app_module.get_redis():
        try:
            redis_client = app_module.get_redis()
            for key in redis_client.keys("game:*:state"):
                redis_client.delete(key)
            for key in redis_client.keys("roles:*"):
                redis_client.delete(key)
            for key in redis_client.keys("voice:*"):
                redis_client.delete(key)
            redis_client.delete("current_session_game_id")
        except Exception as e:
            print(f"Warning: Could not reset Redis: {e}")

    app_module.GAME_STATES.clear()
    app_module.CURRENT_SESSION_GAME_ID = None
    app_module.PARTICIPANT_ROLES.clear()
    app_module.VOICE_PARTICIPANTS.clear()


@pytest.fixture
def reset_globals():
    """Reset Redis and in-memory state between tests."""
    import app as app_module

    _reset_app_globals(app_module)
    yield
    _reset_app_globals(app_module)

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
    
    def _create_game(game_id, chosen_card=None):
        """Insert a game record into games and a round 1 card into rounds."""
        if chosen_card is None:
            chosen_card = 1

        with app_module.get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO games (id, created_at) VALUES (%s, NOW())",
                (game_id,)
            )
            cursor.execute(
                """
                INSERT INTO rounds (game_id, round_number, chosen_card_id, started_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (game_id, 1, chosen_card)
            )
        return game_id
    
    return _create_game