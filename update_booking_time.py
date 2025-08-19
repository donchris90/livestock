from app import create_app, db
from app.models import BookingRequest
from datetime import datetime

app = create_app()
app.app_context().push()

# Update all bookings with combined datetime
bookings = BookingRequest.query.all()
for booking in bookings:
    if booking.date and booking.time:
        booking.booking_time = datetime.combine(booking.date, booking.time)

db.session.commit()
print("All booking_time fields populated.")
