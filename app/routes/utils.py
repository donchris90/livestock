from flask import redirect, url_for, current_app
from threading import Thread
from flask_mail import Message
from app.extensions import mail , db # ✅ Correct import for mail from your own app
from app.models import Notification
# Role-based redirection helper
def redirect_role_dashboard(role):
    if role == 'agent':
        return redirect(url_for('agents.agent_dashboard'))
    elif role == 'vet':
        return redirect(url_for('vets.vet_dashboard'))
    elif role == 'logistics':
        return redirect(url_for('logistics.logistics_dashboard'))
    elif role in ['buyer', 'seller']:
        return redirect(url_for('dashboard.my_dashboard'))
    else:
        return redirect(url_for('dashboard.home'))

# Asynchronous email sender
def send_async_email(msg):
    with current_app.app_context():
        mail.send(msg)

def send_email(subject, recipients, body):
    msg = Message(subject, recipients=recipients)
    msg.body = body
    mail.send(msg)

def create_notification(user_id, message):
    notif = Notification(user_id=user_id, message=message)
    db.session.add(notif)

import uuid

def generate_reference():
    """Generates a unique reference for each Paystack transaction."""
    return f"ESCROW_{uuid.uuid4().hex[:12].upper()}"
