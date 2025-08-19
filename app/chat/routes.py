from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_, desc, func
from app.models import Message, User
from app.extensions import db
import  os
from datetime import datetime
from werkzeug.utils import secure_filename

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

@chat_bp.route('/inbox')
@login_required
def inbox():
    messages = (
        db.session.query(Message)
        .filter(or_(
            Message.sender_id == current_user.id,
            Message.receiver_id == current_user.id
        ))
        .order_by(desc(Message.timestamp))
        .all()
    )

    conversations = {}
    for msg in messages:
        other_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        if other_id not in conversations:
            conversations[other_id] = msg

    unread_counts = (
        db.session.query(Message.sender_id, func.count(Message.id))
        .filter_by(receiver_id=current_user.id, is_read=False)
        .group_by(Message.sender_id)
        .all()
    )
    unread_map = {sender_id: count for sender_id, count in unread_counts}

    contact_ids = list(conversations.keys())
    contacts = User.query.filter(User.id.in_(contact_ids)).all()
    contact_map = {c.id: c for c in contacts}

    chat_summary = []
    for uid, last_msg in conversations.items():
        chat_summary.append({
            'user': contact_map[uid],
            'last_message': last_msg.content,
            'timestamp': last_msg.timestamp,
            'unread': unread_map.get(uid, 0)
        })

    return render_template('chat/inbox.html', chats=chat_summary)


@chat_bp.route('/chat/<int:receiver_id>')
@login_required
def chat_with_user(receiver_id):
    receiver = User.query.get_or_404(receiver_id)

    # Get all messages between current user and receiver
    chat_messages = Message.query.filter(
        or_(
            (Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id),
            (Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id)
        )
    ).order_by(Message.timestamp).all()

    # ✅ Mark unread as read
    unread = Message.query.filter_by(receiver_id=current_user.id, sender_id=receiver_id, is_read=False).all()
    for msg in unread:
        msg.is_read = True
    db.session.commit()

    return render_template(
        'chat/chat.html',
        user=current_user,
        receiver=receiver,
        receiver_id=receiver.id,
        receiver_name=f"{receiver.first_name} {receiver.last_name}",
        chat_messages=chat_messages
    )

@chat_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    file = request.files.get('file')
    receiver_id = request.form.get('receiver_id')

    if not file or not receiver_id:
        return jsonify({'error': 'Missing file or receiver'}), 400

    filename = secure_filename(file.filename)
    folder = os.path.join(current_app.root_path, 'static/uploads/chat_files')
    os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, filename)
    file.save(path)

    msg = Message(
        sender_id=current_user.id,
        receiver_id=int(receiver_id),
        content=f"[File] /static/uploads/chat_files/{filename}",
        timestamp=datetime.utcnow()
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({'message': msg.to_dict()})
