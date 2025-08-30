from datetime import datetime, timedelta
from app.models import  Product
from flask_socketio import SocketIO,socketio

def notify_booking_parties(agent_id, buyer_id, product_id=None):
    from app.models import Notification, Product
    from app.extensions import db,socketio

    notifications = []

    agent_note = Notification(
        user_id=agent_id,
        sender_id=buyer_id,
        message="📅 New booking request received!",
        type='booking',
        is_read=False
    )
    db.session.add(agent_note)
    notifications.append((agent_id, agent_note.message))

    if product_id:
        product = Product.query.get(product_id)
        if product and product.user_id != agent_id:
            seller_note = Notification(
                user_id=product.user_id,
                sender_id=buyer_id,
                message="📦 Your product received a booking via an agent.",
                type='booking',
                is_read=False
            )
            db.session.add(seller_note)
            notifications.append((product.user_id, seller_note.message))

    db.session.commit()

    for user_id, message in notifications:
        socketio.emit('new_notification', {
            'message': message,
            'user_id': user_id
        }, room=str(user_id))

def check_featured_expiry():
    now = datetime.utcnow()
    warning_threshold = now + timedelta(days=3)  # Products expiring within 3 days

    # Query all featured products
    featured_products = Product.query.filter_by(is_featured=True).all()

    for product in featured_products:
        user = product.user  # Assuming relationship: product.user
        status = None
        message = None

        if product.featured_expiry and product.featured_expiry < now:
            status = 'expired'
            message = f'Your featured product "{product.title}" has expired.'
        elif product.featured_expiry and product.featured_expiry <= warning_threshold:
            status = 'expiring_soon'
            message = f'Your featured product "{product.title}" is expiring soon.'

        if status and message:
            # Emit notification to seller
            socketio.emit('featured_notification', {
                'message': message,
                'status': status
            }, room=f"user_{user.id}")