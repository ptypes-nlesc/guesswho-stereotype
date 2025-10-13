from app import socketio, app
import os
os.makedirs('data', exist_ok=True)
# Local testing: allow unsafe werkzeug (not for production)
socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
