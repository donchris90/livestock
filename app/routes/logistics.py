from flask import Blueprint, request, jsonify, render_template, flash, url_for, redirect, session
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db,  User,LogisticsProfile,LogisticsBooking,BookingRequest,Product,Notification, Message
from flask_login import login_required, current_user
from datetime import  datetime, timedelta
from app.utils.email_utils import send_email,mail
logistics_bp = Blueprint('logistics', __name__, url_prefix='/logistics')


@logistics_bp.route('/dashboard')
@login_required
def logistics_dashboard():
    if current_user.role != 'logistics':
        return "Unauthorized", 403

    # Show only bookings assigned to current logistics user
    bookings = LogisticsBooking.query.filter_by(logistics_id=current_user.id).order_by(LogisticsBooking.created_at.desc()).all()

    return render_template('logistics/dashboard.html', bookings=bookings)


@logistics_bp.route('/booking/<int:booking_id>')
@login_required
def view_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)

    if booking.logistics_id != current_user.id:
        return "Unauthorized", 403

    return render_template('logistics/view_booking.html', booking=booking)


@logistics_bp.route('/booking/<int:booking_id>/accept', methods=['POST'])
@login_required
def accept_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)

    if booking.logistics_id != current_user.id:
        return "Unauthorized", 403

    booking.status = 'accepted'
    db.session.commit()
    flash('Booking accepted.', 'success')
    return redirect(url_for('logistics.logistics_dashboard'))


@logistics_bp.route('/booking/<int:booking_id>/reject', methods=['POST'])
@login_required
def reject_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)

    if booking.logistics_id != current_user.id:
        return "Unauthorized", 403

    booking.status = 'rejected'
    db.session.commit()
    flash('Booking rejected.', 'warning')
    return redirect(url_for('logistics.logistics_dashboard'))


@logistics_bp.route('/profile')
@login_required
def logistics_profile():
    if current_user.role != 'logistics':
        return "Unauthorized", 403

    return render_template('logistics/profile.html', logistics=current_user.logistics_profile)

@logistics_bp.route('/search-logistics')
def search_logistics():
    state = request.args.get('state')
    city = request.args.get('city')
    services = request.args.getlist('services')

    query = User.query.join(LogisticsProfile).filter(User.role == 'logistics')

    if state:
        query = query.filter(User.state == state)
    if city:
        query = query.filter(User.city == city)
    if services:
        for service in services:
            query = query.filter(LogisticsProfile.services.any(service))

    results = query.all()
    return render_template("logistics/search_results.html", logistics=results)

@logistics_bp.route('/requests')
@login_required
def incoming_requests():
    # Fetch pending logistics jobs for this logistics provider
    return render_template('logistics/requests.html')

@logistics_bp.route('/completed')
@login_required
def completed_deliveries():
    # Fetch completed deliveries
    return render_template('logistics/completed.html')

@logistics_bp.route('/view-requests')
@login_required
def view_requests():
    if current_user.role != 'logistics':
        return "Unauthorized", 403
    # Fetch requests from database if needed
    return render_template('logistics/view_requests.html')

@logistics_bp.route('/view-reviews')
@login_required
def view_reviews():
    if current_user.role != 'logistics':
        return "Unauthorized", 403
    # Optional: Fetch logistics-related reviews from the database
    return render_template('logistics/view_reviews.html')

@logistics_bp.route('/appointments')
def appointments():
    return render_template('logistics/appointments.html')

@logistics_bp.route('/track-delivery')
def track_delivery():
    return render_template('logistics/track_delivery.html')

@logistics_bp.route('/analytics')
def analytics():
    return render_template('logistics/analytics.html')

@logistics_bp.route('/transaction-history')
def transaction_history():
    return render_template('logistics/transaction_history.html')

@logistics_bp.route('/wallet')
def wallet():
    return render_template('logistics/wallet.html')

@logistics_bp.route('/contact')
def contact():
    return render_template('support/contact.html')

@logistics_bp.route('/notifications')
@login_required
def logistics_notifications():
    # You can replace this with real DB logic
    notifications = [
        {'message': 'New delivery request received', 'timestamp': '2025-08-06 14:00'},
        {'message': 'Customer marked delivery as completed', 'timestamp': '2025-08-05 09:30'},
    ]
    return render_template('logistics/notifications.html', notifications=notifications)




# This should be in logistics_bp or the blueprint handling logistics booking

@logistics_bp.route('/book-logistics/<int:logistics_id>/<int:product_id>', methods=['POST'])
@login_required
def book_logistics(logistics_id, product_id):
    if request.method == 'POST':
        data = request.form
        pickup_address = data.get('pickup_address')
        delivery_address = data.get('delivery_address')
        distance_km = data.get('distance_km')
        estimated_cost = data.get('estimated_cost')

        booking = LogisticsBooking(
            requester_id=current_user.id,
            buyer_id=current_user.id,
            logistics_id=logistics_id,
            product_id=product_id,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            distance_km=distance_km,
            estimated_cost=estimated_cost,
            status='pending',
            created_at=datetime.utcnow()
        )
        db.session.add(booking)
        db.session.commit()

        flash("Booking request submitted successfully", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))  # or any appropriate redirect

    # GET request fallback
    return render_template('logistics/book_logistics_form.html', product_id=product_id, logistics_id=logistics_id)



from flask_mail import Message
from datetime import datetime

@logistics_bp.route('/book-service/<string:role>/<int:provider_id>/<int:product_id>', methods=['POST'])
@login_required
def book_service(role, provider_id, product_id):
    product = Product.query.get_or_404(product_id)
    provider = User.query.get_or_404(provider_id)

    if role == 'agent':
        booking = BookingRequest(
            agent_id=provider.id,
            buyer_id=current_user.id,
            product_id=product.id,
            status='pending'
        )
        db.session.add(booking)
        db.session.commit()

        # Email to agent
        msg = Message("New Agent Booking Request",
                      recipients=[provider.email])
        msg.body = f"Hello {provider.first_name},\n\nYou have a new agent booking request for the product \"{product.title}\" from {current_user.first_name} {current_user.last_name}.\n\nPlease log in to your dashboard to respond."
        mail.send(msg)

        # Dashboard notification
        notification = Notification(
            user_id=provider.id,
            message=f"You have a new agent booking request for '{product.title}'",
            link=f"/agent/bookings",  # adjust to your actual route
            is_read=False,
            timestamp=datetime.utcnow()
        )
        db.session.add(notification)

    elif role == 'logistics':
        booking = LogisticsBooking(
            logistics_id=provider.id,
            buyer_id=current_user.id,
            product_id=product.id,
            status='pending'
        )
        db.session.add(booking)
        db.session.commit()

        # Email to logistics provider
        msg = Message("New Logistics Booking Request",
                      recipients=[provider.email])
        msg.body = f"Hello {provider.first_name},\n\nYou have a new logistics request for the product \"{product.title}\" from {current_user.first_name} {current_user.last_name}.\n\nPlease log in to your dashboard to accept or reject."
        mail.send(msg)

        # Dashboard notification
        notification = Notification(
            user_id=provider.id,
            message=f"You have a new logistics request for '{product.title}'",
            link=f"/logistics/bookings",  # adjust to your actual route
            is_read=False,
            timestamp=datetime.utcnow()
        )
        db.session.add(notification)

    else:
        flash("Invalid role.", "danger")
        return redirect(request.referrer)

    db.session.commit()

    return jsonify({'message': f'{role.capitalize()} booking request sent!'})


@logistics_bp.route('/logistics/booking-confirmation')
@login_required
def search_logistics_page():
    return render_template('logistics/booking_confirmation.html')  # Create this template



# In logistics_routes.py or equivalent
@logistics_bp.route('/my_bookings')
@login_required
def view_logistics_bookings():
    user_id = current_user.id

    # Optional status filter from query param
    status = request.args.get('status')  # pending or completed
    query = LogisticsBooking.query.filter_by(buyer_id=user_id)

    if status:
        query = query.filter_by(status=status)

    bookings = query.order_by(LogisticsBooking.created_at.desc()).all()
    return render_template('my_bookings.html', bookings=bookings, status_filter=status
                           )

@logistics_bp.route('/logistics/bookings')
@login_required
def view_driver_bookings():
    user_id = current_user.id
    # Fetch bookings assigned to this logistics driver
    bookings = LogisticsBooking.query.filter_by(logistics_id=user_id).order_by(LogisticsBooking.created_at.desc()).all()
    return render_template('logistics/view_driver_bookings.html', bookings=bookings)

@logistics_bp.route('/complete-booking/<int:booking_id>', methods=['POST'])
@login_required
def complete_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)

    # Optional: Check that current user is the one assigned to the booking
    if booking.logistics_id != current_user.id:
        flash("You are not authorized to complete this booking.", "danger")
        return redirect(request.referrer or url_for('logistics.view_driver_bookings'))

    # Update status
    booking.status = 'completed'
    db.session.commit()

    flash("Booking marked as completed.", "success")
    return redirect(request.referrer or url_for('logistics.view_driver_bookings'))


@logistics_bp.route('/cancel-booking/<int:booking_id>', methods=['POST', 'GET'])
def cancel_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)

    # Optional: Check if the logged-in user is allowed to cancel
    # if booking.logistics_user_id != current_user.id:
    #     flash('Unauthorized', 'danger')
    #     return redirect(url_for('logistics.logistics_dashboard'))

    booking.status = 'cancelled'
    db.session.commit()
    flash('Booking has been cancelled.', 'success')
    return redirect(request.referrer or url_for('logistics.logistics_dashboard'))





# Accept Booking
@logistics_bp.route('/driver/accept-booking/<int:booking_id>', methods=['POST'])
@login_required
def driver_accept_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)
    if booking.status == 'pending':
        booking.status = 'accepted'
        db.session.commit()

        # Get buyer details
        buyer = User.query.get(booking.buyer_id)
        driver_name = current_user.first_name or "Driver"

        # Send email to buyer
        if buyer and buyer.email:
            subject = "Your Logistics Booking was Accepted"
            message = render_template('logistics/booking_accepted.html', driver=driver_name, booking=booking)
            send_email(buyer.email, subject, message)

        # Dashboard notification
        if buyer:
            notif = Notification(
                user_id=buyer.id,
                message=f"Your logistics request has been accepted by {driver_name}.",
                timestamp=datetime.utcnow()
            )
            db.session.add(notif)
            db.session.commit()

        flash('Booking accepted.', 'success')

    return redirect(url_for('logistics.view_driver_bookings'))


# Reject Booking
@logistics_bp.route('/driver/reject-booking/<int:booking_id>', methods=['POST'])
@login_required
def driver_reject_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)
    if booking.status == 'pending':
        booking.status = 'rejected'
        db.session.commit()

        # Get buyer details
        buyer = User.query.get(booking.buyer_id)
        driver_name = current_user.first_name or "Driver"

        # Send email to buyer
        if buyer and buyer.email:
            subject = "Your Logistics Booking was Rejected"
            message = render_template('emails/booking_rejected.html', driver=driver_name, booking=booking)
            send_email(buyer.email, subject, message)

        # Dashboard notification
        if buyer:
            notif = Notification(
                user_id=buyer.id,
                message=f"Your logistics request was rejected by {driver_name}.",
                timestamp=datetime.utcnow()
            )
            db.session.add(notif)
            db.session.commit()

        flash('Booking rejected.', 'warning')

    return redirect(url_for('logistics.driver_bookings'))

@logistics_bp.route('/driver-reject-booking/<int:booking_id>', methods=['POST'])
@login_required
def reject_driver_booking(booking_id):
    booking = LogisticsBooking.query.get_or_404(booking_id)

    if booking.status == 'pending':
        booking.status = 'rejected'
        db.session.commit()

        # Email notification
        requester = User.query.get(booking.requester_id)
        if requester and requester.email:
            msg = Message("Logistics Booking Rejected",
                          recipients=[requester.email])
            msg.body = f"Hello {requester.first_name},\n\nUnfortunately, your logistics booking (ID: {booking.id}) was rejected by the driver.\n\nYou can try booking with another driver."
            mail.send(msg)

        # Dashboard notification
        notification = Notification(
            user_id=booking.requester_id,
            message=f"Your logistics booking ID {booking.id} was rejected by the driver.",
            timestamp=datetime.utcnow(),
            is_read=False
        )
        db.session.add(notification)
        db.session.commit()

        flash('Booking rejected.', 'warning')

    return redirect(url_for('logistics.driver_dashboard'))

@logistics_bp.route('/kyc', methods=['GET', 'POST'])
@login_required
def kyc():
    if current_user.role != 'logistics':
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    # Render KYC upload page
    return render_template('logistics/kyc.html', user=current_user)