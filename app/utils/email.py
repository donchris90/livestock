# utils/email.py
from flask import current_app
import smtplib
from email.message import EmailMessage

def send_email(to, subject, body, html=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = current_app.config["MAIL_USERNAME"]

    if isinstance(to, (list, tuple)):
        msg["To"] = ", ".join(to)
    else:
        msg["To"] = to

    msg.set_content(body)

    if html:
        msg.add_alternative(html, subtype='html')

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(
            current_app.config["MAIL_USERNAME"],
            current_app.config["MAIL_PASSWORD"]
        )
        server.send_message(msg)
