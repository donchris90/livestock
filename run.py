import os
from app import create_app, socketio

# ---------- Create Flask App ----------
app = create_app()

# ---------- For local development ----------
if __name__ == "__main__":
    # Use PORT environment variable if set, otherwise default to 5000
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # Run using SocketIO for WebSocket support locally
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True  # Needed for Flask 3.x
    )

# ---------- For Render / Gunicorn ----------
# Gunicorn command (Render start command):
# gunicorn run:app --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT
# Gunicorn will automatically use the `app` object exposed above
# SocketIO will detect Eventlet and work correctly
