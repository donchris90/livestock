from flask import Blueprint, request, jsonify
from app.models import User, Subscription, db
from datetime import datetime, timedelta

paystack_webhook_bp = Blueprint('paystack_webhook', __name__)

@paystack_webhook_bp.route('/paystack/webhook', methods=['POST'])
def paystack_webhook():
    data = request.get_json()
    print("Webhook received:", data)  # Optional debug log

    if data.get('event') == 'charge.success':
        email = data['data']['customer']['email']
        plan_name = data['data']['metadata']['plan']
        user = User.query.filter_by(email=email).first()

        if user:
            new_subscription = Subscription(
                user_id=user.id,
                plan_name=plan_name,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                grace_end=datetime.utcnow() + timedelta(days=35)
            )
            db.session.add(new_subscription)
            user.plan_name = plan_name
            db.session.commit()

    return jsonify({"status": "success"})
