from app.models import Subscription, User
from datetime import datetime, timedelta
from app.extensions import db

user = User.query.get(1)  # test user
sub = Subscription(
    user_id=user.id,
    plan='Starter',
    start_date=datetime.utcnow(),
    end_date=datetime.utcnow() + timedelta(days=3),
    grace_end=datetime.utcnow() + timedelta(days=10)
)
db.session.add(sub)
db.session.commit()
