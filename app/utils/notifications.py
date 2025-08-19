def notify_booking_parties(agent_id, buyer_id, product_id=None):
    from app.models import Notification, Product
    from app.extensions import db, socketio

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
