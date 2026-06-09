# wsgi.py
import os

from gevent import monkey
monkey.patch_all()

from app import app, socketio

if __name__ == "__main__":
    try:
        port = int(os.getenv("APP_PORT", "5000"))
    except ValueError:
        port = 5000
    socketio.run(app, host="0.0.0.0", port=port, debug=False)