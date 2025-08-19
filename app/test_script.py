# test_script.py
from app import create_app
from app.models import User
from app.extensions import db

app = create_app()

with app.app_context():
    # This works fine
    user = User.query.first()
    print(user.email)
