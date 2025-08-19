from flask_mail import Message
from threading import Thread
from flask import current_app
from app.extensions import mail
from app.models import User

def send_async_email(msg):
    with current_app.app_context():
        mail.send(msg)

def send_email_to_agent(booking):
    agent = User.query.get(booking.agent_id)

    if not agent or not agent.email:
        return

    subject = f"Inspection Completed - Booking #{booking.id}"
    recipient = agent.email
    body = f"""
Hello {agent.first_name},

The buyer has marked Booking #{booking.id} as complete.

Inspection Report:
{booking.inspection_report}

Outcome: {booking.inspection_outcome or 'Not specified'}

Please login to your dashboard for more details.

Regards,
Livestock Farm App
"""
    msg = Message(subject=subject, recipients=[recipient], body=body)
    Thread(target=send_async_email, args=(msg,)).start()
