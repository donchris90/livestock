# app/utils/email_utils.py

from flask_mail import Message
from flask import render_template
from app import mail

def send_email(to, subject, body=None, html=None, template=None, context=None):
    try:
        msg = Message(subject, recipients=[to])

        # Render email content
        if template and context:
            msg.html = render_template(template, **context)
        elif html:
            msg.html = html

        # Fallback plain text
        if body:
            msg.body = body
        else:
            msg.body = "This is an automated email from FarmApp."

        mail.send(msg)
        print(f"✅ Email sent to {to}")
    except Exception as e:
        print(f"❌ Error sending email: {e}")

