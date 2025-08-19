from flask_socketio import emit
from app.extensions import socketio, mail
from flask_mail import Message
from flask import current_app

def notify_agent_inspection_marked_complete(booking):
    # Real-time toast notification
    message = f"✅ Buyer has marked Booking #{booking.id} as complete."
    room = f"user_{booking.agent_id}"

    socketio.emit(
        'inspection_notification',
        {'message': message},
        namespace='/notifications',
        to=room
    )

    # Email notification to agent
    if booking.agent and booking.agent.email:
        try:
            msg = Message(
                subject=f"Booking #{booking.id} Marked as Complete",
                recipients=[booking.agent.email],
                body=f"""
Dear {booking.agent.first_name},

The buyer has marked the inspection for Booking #{booking.id} as complete.

Please review the outcome on your dashboard.

Regards,
Livestock Farm Team
                """
            )
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Email sending failed: {e}")
