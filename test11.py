from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, abort, current_app

test_bp = Blueprint('test', __name__, )
@test_bp.route('/create-admin-once')
def create_admin_once():
    from app.models import User
    from app import db
    from werkzeug.security import generate_password_hash

    if User.query.filter_by(email='admin@example.com').first():
        return "⚠️ Admin already exists."

    admin = User(
        first_name='Admin',
        last_name='User',
        email='admin@example.com',
        phone='08000000000',
        role='admin',
        state='Lagos',
        city='Ikeja',
        street='Admin Street',
        password_hash=generate_password_hash('happen'),

        is_verified=True,
        is_active=True
    )

    db.session.add(admin)
    db.session.commit()
    return "✅ Admin user created."