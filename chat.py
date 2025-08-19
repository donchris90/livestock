from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from app.extensions import db

from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://postgres:Happen123!@localhost:5432/livestockdb'  # replace with your PostgreSQL URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150))  # store hashed passwords in real app

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'content': self.content,
            'timestamp': self.timestamp.isoformat()
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Routes for auth (demo only)
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    # Skipping password check for demo - add hashing + verification in real app
    login_user(user)
    return jsonify({'status': 'logged_in', 'user_id': user.id})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'status': 'logged_out'})


# Chat APIs
@app.route('/chat/send', methods=['POST'])
@login_required
def send_message():
    data = request.json
    receiver_id = data.get('receiver_id')
    content = data.get('content')
    if not receiver_id or not content:
        return jsonify({'error': 'Missing receiver_id or content'}), 400

    msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()

    return jsonify({'status': 'success', 'message': msg.to_dict()}), 201

@app.route('/chat/messages/<int:user_id>', methods=['GET'])
@login_required
def get_messages(user_id):
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    return jsonify([msg.to_dict() for msg in msgs])


# Setup DB and some test users (run once)
@app.before_first_request
def create_tables():
    db.create_all()
    if not User.query.filter_by(username='alice').first():
        db.session.add(User(username='alice'))
    if not User.query.filter_by(username='bob').first():
        db.session.add(User(username='bob'))
    db.session.commit()


if __name__ == '__main__':
    app.run(debug=True)
