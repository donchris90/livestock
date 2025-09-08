import os
from app import create_app, socketio
from flask_socketio import SocketIO, join_room, leave_room, emit


# ---------- Create Flask App ----------
app = create_app()

# Start scheduler after app creation
from app.utils.notifications import check_featured_expiry
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(check_featured_expiry, 'interval', hours=1)
scheduler.start()

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

# 🟢 Place your join handler here
@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        room = f'user_{user_id}'
        join_room(room)
        print(f"User {user_id} joined room {room}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() == "true"

    # Enable auto-reload with debug=True
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=True,            # This enables auto-reload
        allow_unsafe_werkzeug=True    # Needed for Flask 3.x
    )
