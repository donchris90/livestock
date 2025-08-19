from flask_socketio import emit, join_room
from flask_login import current_user
from app.models import Message, db, User
from datetime import datetime
from app.extensions import socketio


def register_chat_events(socketio):

    @socketio.on('join')
    def handle_join(data):
        """
        Join chat room and personal user room
        """
        room = data.get('room')
        user_id = data.get('user_id')

        if room:
            join_room(room)
            print(f"✅ Joined chat room: {room}")

        if user_id:
            personal_room = f"user_{user_id}"
            join_room(personal_room)
            print(f"✅ Joined personal room: {personal_room}")

    @socketio.on('send_message')
    def handle_send(data):
        """
        Save message to DB and emit to both sender and receiver
        """
        sender_id = data.get('sender_id')
        receiver_id = data.get('receiver_id')
        content = data.get('content')
        image_url = data.get('image_url')  # Optional
        # room = data.get('room')  # No longer needed to emit to shared room

        if not sender_id or not receiver_id:
            print("❌ Missing sender or receiver ID")
            return

        # Determine actual content to store
        message_content = f"[File] {image_url}" if image_url else content

        # Save message
        message = Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=message_content,
            timestamp=datetime.utcnow()
        )
        db.session.add(message)
        db.session.commit()

        msg_dict = message.to_dict()

        # Emit to both users' personal rooms
        sender_room = f"user_{sender_id}"
        receiver_room = f"user_{receiver_id}"

        emit('receive_message', msg_dict, to=sender_room)
        emit('receive_message', msg_dict, to=receiver_room)

        # Send new message notification to receiver
        sender = User.query.get(sender_id)
        sender_name = f"{sender.first_name} {sender.last_name}" if sender else "Unknown"

        emit('new_notification', {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'sender_name': sender_name,
            'content': content or '[File]'
        }, to=receiver_room)

        # Send inbox update
        emit('update_inbox', {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'last_message': content or '[File]',
            'timestamp': msg_dict['timestamp']
        }, to=receiver_room)

    @socketio.on('mark_seen')
    def handle_mark_seen(data):
        """
        Mark messages from sender as seen by receiver
        """
        sender_id = data.get('sender_id')
        receiver_id = data.get('receiver_id')

        if not sender_id or not receiver_id:
            print("❌ Missing IDs for mark_seen")
            return

        messages = Message.query.filter_by(
            sender_id=sender_id,
            receiver_id=receiver_id,
            seen=False
        ).all()

        seen_ids = []
        for msg in messages:
            msg.seen = True
            msg.seen_at = datetime.utcnow()
            seen_ids.append(msg.id)

        db.session.commit()

        emit('messages_seen', {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'seen_ids': seen_ids
        }, to=f"user_{sender_id}")
        print(f"👁️ Seen {len(seen_ids)} messages from {sender_id} to {receiver_id}")

    @socketio.on('connect', namespace='/notifications')
    def handle_connect():
        """
        Join personal room for notifications
        """
        if current_user.is_authenticated:
            room = f"user_{current_user.id}"
            join_room(room)
            print(f"🔔 {current_user.get_full_name()} joined notification room: {room}")


@socketio.on('typing')
def handle_typing(data):
    room = data.get('room')
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')

    emit('typing_preview', {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'message': 'Typing...'
    }, to=f"user_{receiver_id}")

@socketio.on('delete_message')
def handle_delete(data):
    message_id = data.get('message_id')
    user_id = data.get('user_id')
    message = Message.query.get(message_id)
    if message and message.sender_id == user_id:
        db.session.delete(message)
        db.session.commit()
        emit('message_deleted', {'message_id': message_id}, broadcast=True)

@socketio.on('edit_message')
def handle_edit(data):
    message_id = data.get('message_id')
    new_content = data.get('new_content')
    user_id = data.get('user_id')
    message = Message.query.get(message_id)
    if message and message.sender_id == user_id:
        message.content = new_content
        db.session.commit()
        emit('message_edited', {
            'message_id': message_id,
            'new_content': new_content
        }, broadcast=True)
