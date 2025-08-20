import os
from app import create_app, socketio

# ---------- Create Flask App ----------
app = create_app()

# ---------- Run App ----------
if __name__ == "__main__":
    # Render automatically sets PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # Use socketio.run instead of gunicorn in local dev or direct start
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True  # needed for Flask 3.x on dev
    )
