from datetime import datetime, timedelta
from app.models import Subscription
from app.extensions import db

def process_auto_renewals():
    today = datetime.utcnow()
    subscriptions = Subscription.query.filter_by(auto_renew=True, is_active=False).all()
    for sub in subscriptions:
        if sub.end_date < today:
            sub.activate(duration_days=30)
            db.session.add(sub)  # Optional if already tracked
    db.session.commit()
