from flask_login import current_user
from datetime import datetime
from app.models import Notification, ChatMessage, BookingRequest, SubscriptionPlan,EscrowPayment


def init_context_processors(app):
    @app.context_processor
    def inject_dashboard_counts():
        if not current_user.is_authenticated:
            return {
                'unread_count': 0,
                'unread_message_count': 0,
                'pending_outcome_bookings': []
            }

        unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        unread_message_count = ChatMessage.query.filter_by(receiver_id=current_user.id, is_read=False).count()

        pending_outcome_bookings = []
        if current_user.role == 'agent':
            now = datetime.utcnow()
            pending_outcome_bookings = BookingRequest.query.filter(
                BookingRequest.agent_id == current_user.id,
                BookingRequest.booking_time < now,
                BookingRequest.inspection_reported_at == None
            ).all()

        return {
            'unread_count': unread_count,
            'unread_message_count': unread_message_count,
            'pending_outcome_bookings': pending_outcome_bookings
        }

    @app.context_processor
    def inject_subscription_info():
        if current_user.is_authenticated:
            return dict(user_subscription=current_user.subscription)
        return {}

    @app.context_processor
    @app.context_processor
    def inject_upload_limit():
        try:
            if current_user.is_authenticated:
                plan = current_user.subscription_plan or 'Starter'
                subscription = SubscriptionPlan.query.filter_by(name=plan).first()
                upload_limit = subscription.product_limit if subscription else 5
            else:
                upload_limit = 0
        except:
            upload_limit = 0

        return dict(upload_limit=upload_limit)

    @app.context_processor
    def inject_current_time():
        return {'current_time': datetime.utcnow()}
# app/context_processors.py

def get_upload_limit(plan):
    if plan == 'basic':
        return 5
    elif plan == 'premium':
        return 50
    elif plan == 'pro':
        return 200
    else:
        return 1

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow()}

    @app.context_processor
    def inject_escrow_unread_count():
        if current_user.is_authenticated:
            count = EscrowPayment.query.filter_by(
                buyer_id=current_user.id,
                is_read=False
            ).count()
        else:
            count = 0
        return dict(escrow_unread_count=count)