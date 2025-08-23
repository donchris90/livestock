from flask import Blueprint, render_template, flash, redirect, url_for,abort, request, jsonify, current_app

from werkzeug.utils import secure_filename
from datetime import datetime
from app.routes.utils import create_notification,mail
from app.models import EscrowPayment,WalletTransaction
from app.utils.payout_utils import get_or_create_wallet
from app.forms import FeedbackForm
import os
from flask import request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db, socketio
from app.utils.email_utils import send_email
import json
import threading
from app.forms import BookProductForm  # your form
from app.extensions import db, mail, socketio
from app.models import BookingRequest, Notification, Message,LogisticsProfile, User, Product,Review,Order
from app.utils.email import send_email
from app.context_processors import init_context_processors
from app.extensions import socketio
from app.forms import BookingForm
from sqlalchemy import and_
from app.utils.email_utils import send_email
from flask import request, jsonify
from math import radians, cos, sin, asin, sqrt
from app.models import User
from sqlalchemy import func


from flask import Blueprint, request, jsonify
from math import radians, cos, sin, asin, sqrt
from app.models import User

agents_bp = Blueprint('agents', __name__, url_prefix='/agents')


def allowed_file(filename, allowed_exts):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts



@agents_bp.route('/agent-dashboard')
@login_required
def agent_dashboard():
    user = current_user
    page = request.args.get('page', 1, type=int)
    # --- Booking stats ---
    total_bookings = BookingRequest.query.filter_by(agent_id=user.id).count()
    completed_bookings = BookingRequest.query.filter_by(agent_id=user.id, status='completed').count()
    pending_bookings = BookingRequest.query.filter_by(agent_id=user.id, status='pending').count()
    recent_bookings = BookingRequest.query.filter_by(agent_id=user.id)\
        .order_by(BookingRequest.date.desc()).limit(5).all()

    # --- Revenue Summary (Orders + Escrow) ---
    # Orders
    total_earned_orders = db.session.query(func.sum(Order.agreed_price))\
        .filter(Order.agent_id == user.id, Order.status == 'completed').scalar() or 0
    pending_orders = db.session.query(func.sum(Order.agreed_price))\
        .filter(Order.agent_id == user.id, Order.status == 'pending').scalar() or 0

    # Escrow payments
    escrows = EscrowPayment.query.filter(
        EscrowPayment.provider_id == user.id,
        EscrowPayment.type.in_(['agent', 'logistics'])
    ).order_by(EscrowPayment.created_at.desc()).limit(5).all()

    total_escrow_released = sum(e.partial_release_amount or 0 for e in escrows)
    total_escrow_pending = sum((e.amount or 0) - (e.partial_release_amount or 0) for e in escrows)

    # Total earnings including released escrow + direct payments
    total_earned = total_earned_orders + total_escrow_released
    pending_payment = pending_orders + total_escrow_pending

    # --- Ratings / Feedback ---
    average_rating = db.session.query(func.avg(Review.rating))\
        .filter_by(reviewee_id=user.id).scalar()
    average_rating = round(average_rating or 0, 1)

    recent_feedback = Review.query.filter_by(reviewee_id=user.id)\
        .order_by(Review.created_at.desc()).limit(5).all()

    # --- Profile Completion ---
    completed_fields = sum([
        bool(user.profile_picture),
        bool(user.about),
        bool(user.state and user.city),
        bool(user.availability_status),
        bool(user.service_tags),
    ])
    total_fields = 5
    profile_completion = int((completed_fields / total_fields) * 100)
    total_direct_received = db.session.query(func.sum(WalletTransaction.amount)) \
                                .filter(
        WalletTransaction.user_id == user.id,
        WalletTransaction.transaction_type == 'credit',
        WalletTransaction.description.like('Received direct payment%')
    ).scalar() or 0
    # Unread notifications count
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    # Fetch agent's bookings (pending/accepted/etc.)
    bookings_query = BookingRequest.query.filter(
        BookingRequest.agent_id == current_user.id,
        BookingRequest.status.in_(['pending', 'accepted', 'inspection_submitted', 'buyer_confirmed'])
    ).order_by(BookingRequest.date.desc())
    bookings = bookings_query.paginate(page=page, per_page=10)
    # Fetch unread notifications for current user
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.timestamp.desc()).all()

    unread_count = len(notifications)  # or use .count() as before
    # Fetch or create wallet for this agent
    wallet = get_or_create_wallet(user_id=user.id)
    return render_template('agents/dashboard.html',
                           user=user,
                           total_bookings=total_bookings,
                           completed_bookings=completed_bookings,
                           pending_bookings=pending_bookings,
                           recent_bookings=recent_bookings,
                           total_earned=total_earned,
                           pending_payment=pending_payment,
                           escrows=escrows,
                           total_escrow_released=total_escrow_released,
                           total_escrow_pending=total_escrow_pending,
                           average_rating=average_rating,
                           recent_feedback=recent_feedback,
                           notifications=notifications,
                           profile_completion=profile_completion,
                           total_direct_received=total_direct_received,
                           bookings=bookings,
                           unread_count=unread_count,
                           wallet=wallet,
                           )


@agents_bp.route('/mark-notifications-read', methods=['POST'])
@login_required
def mark_notifications_read():
    # Mark all notifications as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for('agents.agent_dashboard'))

@agents_bp.route('/edit-profile')
@login_required
def edit_profile():
    return render_template('agents/edit_profile.html', user=current_user)

from sqlalchemy.orm import joinedload
@agents_bp.route('/profile/<int:agent_id>')
@login_required
def agent_profile(agent_id):
    agent = User.query.filter_by(id=agent_id, role='agent').first()
    if not agent:
        abort(404, description="Agent not found")

    booking = BookingRequest.query.filter_by(agent_id=agent_id, buyer_id=current_user.id).first()

    # ✅ Get reviews where the booking is related to the agent
    reviews = (
        Review.query
        .join(Review.booking)
        .filter(BookingRequest.agent_id == agent_id)
        .options(joinedload(Review.reviewer))
        .all()
    )

    # Group reviews
    positive_reviews = [r for r in reviews if r.rating >= 4]
    negative_reviews = [r for r in reviews if r.rating <= 2]

    # Calculate average
    if reviews:
        average_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)
        total_reviews = len(reviews)
    else:
        average_rating = 0
        total_reviews = 0

    return render_template(
        'agents/agent_profile.html',
        agent=agent,
        booking=booking,
        positive_reviews=positive_reviews,
        negative_reviews=negative_reviews,
        average_rating=average_rating,
        total_reviews=total_reviews,


    )


@agents_bp.route('/appointments')
@login_required
def view_appointments():
    return render_template('agents/appointments.html', user=current_user)


@agents_bp.route('/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat_with_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        content = request.form.get('message')
        if content:
            msg = Message(sender_id=current_user.id, receiver_id=user_id, content=content)
            db.session.add(msg)
            db.session.commit()

    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()

    return render_template('agents/chat.html', user=user, messages=messages)


# app/agents/routes.py

@agents_bp.route('/notifications')
@login_required
def agent_notifications():
    # Fetch all notifications
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()

    # Mark all unread notifications as read
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    for n in unread:
        n.is_read = True
    db.session.commit()

    return render_template('agents/notifications.html', notifications=notifications)


@agents_bp.route('/book-agent/<int:agent_id>/<int:product_id>', methods=['GET', 'POST'])
@login_required
def book_agent(agent_id, product_id):
    agent = User.query.get_or_404(agent_id)
    product = Product.query.get_or_404(product_id)
    form = BookingForm()

    # Prefill product_id in form
    if request.method == 'GET':
        form.product_id.data = product.id

    reviews = Review.query.filter_by(reviewee_id=agent_id).all()

    if form.validate_on_submit():
        booking = BookingRequest(
            buyer_id=current_user.id,
            agent_id=agent.id,
            seller_id=product.user_id,
            product_id=product.id,
            booking_time=datetime.utcnow(),
            date=form.date.data,
            message=form.message.data,
            status='pending'
        )
        db.session.add(booking)
        db.session.commit()

        # Notifications
        msg = f"New inspection booking #{booking.id} by {current_user.first_name} for product '{product.title}'."
        try:
            if product.user.email:
                send_email([product.user.email], "New Inspection Booking", msg)
            if agent.email:
                send_email([agent.email], "New Inspection Booking Assigned", msg)
        except Exception as e:
            print(f"Email sending failed: {e}")

        try:
            create_notification(product.user_id, msg)
            create_notification(agent.id, msg)
        except Exception as e:
            print(f"Notification creation failed: {e}")

        flash("Booking request sent!", "success")
        return redirect(url_for('agents.booking_confirmation', booking_id=booking.id))

    return render_template('agents/book_agent.html', form=form, agent=agent, product=product, reviews=reviews)


@agents_bp.route('/bookings', methods=['GET', 'POST'])
@login_required
def agent_bookings():
    filter_type = request.args.get('filter', 'upcoming')
    page = request.args.get('page', 1, type=int)

    # Handle Accept / Reject bookings
    if request.method == 'POST':
        booking_id = request.form.get('booking_id')
        action = request.form.get('action')  # 'accepted' or 'rejected'
        booking = BookingRequest.query.get_or_404(booking_id)

        if booking.agent_id != current_user.id or action not in ['accepted', 'rejected']:
            flash("Invalid action.", "danger")
            return redirect(url_for('agents.agent_bookings', filter=filter_type, page=page))

        booking.status = action
        db.session.commit()
        db.session.refresh(booking)  # Force fresh data

        # Socket.IO notification to buyer
        socketio.emit(
            'booking_update',
            {
                'user_id': booking.buyer_id,
                'message': f"Booking #{booking.id} has been {action} by the agent."
            },
            namespace='/notifications',
            room=str(booking.buyer_id)  # Ensure you use room per user_id
        )

        # Email notification
        if booking.buyer and booking.buyer.email:
            send_email(
                to=booking.buyer.email,
                subject=f"Booking #{booking.id} {action.capitalize()} by Agent",
                body=f"Dear {booking.buyer.first_name},\n\nYour booking #{booking.id} has been {action} by the agent.\n\nThank you."
            )

        flash(f"Booking #{booking.id} has been {action}.", "success")
        return redirect(url_for('agents.agent_bookings', filter=filter_type, page=page))

    # Fetch bookings for dashboard
    if filter_type == 'completed':
        bookings_query = BookingRequest.query.filter_by(agent_id=current_user.id, status='buyer_confirmed')
    else:
        bookings_query = BookingRequest.query.filter(
            BookingRequest.agent_id == current_user.id,
            BookingRequest.status.in_(['pending', 'accepted', 'inspection_submitted'])
        )

    bookings = bookings_query.order_by(BookingRequest.date.desc()).paginate(page=page, per_page=10)

    # Unread notifications
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.timestamp.desc()).all()
    unread_count = len(notifications)

    return render_template(
        'agents/booking_dashboard.html',
        bookings=bookings,
        filter_type=filter_type,
        notifications=notifications,
        unread_count=unread_count
    )

@agents_bp.route('/booking-confirmation/<int:booking_id>')
@login_required
def booking_confirmation(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)
    return render_template('agents/booking_confirmation.html', booking=booking)



@agents_bp.route('/booking/<int:booking_id>/update', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)

    # Ensure the agent is allowed
    if booking.agent_id != current_user.id:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('agents.agent_bookings'))

    action = request.form.get('action')
    if action not in ['accepted', 'rejected']:
        flash("Invalid action submitted.", "warning")
        return redirect(url_for('agents.agent_bookings'))

    # Update booking status
    booking.status = action
    db.session.commit()

    buyer = booking.buyer
    agent = booking.agent  # You can also use current_user

    # MESSAGE for notification and email
    notif_message = f"📢 Your booking was {action.upper()} by Agent {current_user.first_name}"

    # ===================== ✅ Notification for Buyer =====================
    if buyer:
        buyer_notif = Notification(
            user_id=buyer.id,
            message=notif_message,
            notification_type='booking',
            is_read=False
        )
        db.session.add(buyer_notif)

        # 🔔 Emit Socket.IO to buyer
        socketio.emit('new_notification', {
            'message': notif_message,
            'user_id': buyer.id
        }, room=str(buyer.id))

        # 📧 Send Email to Buyer
        try:
            email_body = (
                f"Dear {buyer.first_name},\n\n"
                f"Your booking request has been {action.upper()} by Agent {current_user.first_name}.\n\n"
                f"Date: {booking.date.strftime('%Y-%m-%d')}\n"
                f"Time: {booking.time.strftime('%I:%M %p') if booking.time else 'N/A'}\n\n"
                "Thank you for using Livestock Farm App."
            )
            send_email(to=buyer.email, subject="Booking Status Update", body=email_body)
        except Exception as e:
            print("Email send error:", e)

    # ===================== ✅ Optional Notification for Agent =====================
    agent_notif = Notification(
        user_id=current_user.id,
        message=f"You have {action} a booking request from {buyer.first_name}",
        notification_type='booking',
        is_read=False
    )
    db.session.add(agent_notif)

    socketio.emit('new_notification', {
        'message': agent_notif.message,
        'user_id': current_user.id
    }, room=str(current_user.id))

    db.session.commit()

    flash(f"Booking {action.capitalize()}!", "success")
    return redirect(url_for('agents.agent_bookings'))



@agents_bp.route('/booking/<int:booking_id>/report-outcome', methods=['GET', 'POST'])
@login_required
def report_booking_outcome(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)

    if booking.agent_id != current_user.id:
        flash("Unauthorized access to report outcome.", "danger")
        return redirect(url_for('agents.agent_bookings'))

    if request.method == 'POST':
        outcome = request.form.get('outcome')
        report = request.form.get('report')

        if not outcome:
            flash("Outcome is required.", "danger")
            return redirect(request.referrer)

        photos = request.files.getlist('photos')
        photo_filenames = booking.inspection_photos or []

        for photo in photos:
            if photo and photo.filename != '':
                filename = secure_filename(photo.filename)
                photo_path = os.path.join(current_app.root_path, 'static/uploads/inspection_files', filename)
                photo.save(photo_path)
                photo_filenames.append(filename)

        booking.inspection_outcome = outcome
        booking.inspection_report = report
        booking.inspection_reported_at = datetime.utcnow()
        booking.inspection_photos = photo_filenames

        db.session.commit()

        if booking.buyer and booking.buyer.email:
            send_email(
                to=booking.buyer.email,
                subject="Inspection Report Available",
                body=f"""
Hello {booking.buyer.first_name},

Agent {current_user.first_name} has submitted an inspection outcome for your recent booking.

📝 Outcome: {booking.inspection_outcome}
📄 Report: {booking.inspection_report or 'No detailed report provided'}

You can log in to view attached files.

Thank you,
Livestock Farm App
"""
            )

        flash("Inspection outcome submitted successfully.", "success")
        return redirect(url_for('agents.agent_bookings', filter='past'))

    return render_template('agents/report_outcome.html', booking=booking)


UPLOAD_FOLDER = 'static/uploads/inspection_photos'

@agents_bp.route('/submit-inspection/<int:booking_id>', methods=['POST'])
@login_required
def submit_inspection(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)

    # Only the assigned agent can submit
    if booking.agent_id != current_user.id:
        abort(403)

    inspection_report = request.form.get('inspection_report')
    if not inspection_report:
        flash("Inspection report is required.", "danger")
        return redirect(url_for('agents.agent_bookings'))

    booking.inspection_report = inspection_report
    booking.inspection_reported_at = datetime.utcnow()
    booking.status = 'inspection_submitted'  # Updated status
    db.session.commit()

    # Notify buyer and agent via Socket.IO
    for user_id in [booking.buyer_id, booking.agent_id]:
        socketio.emit(
            'inspection_update',
            {'user_id': user_id, 'message': f"Inspection report submitted for booking #{booking.id}."},
            namespace='/notifications'
        )

    # Email notification
    recipients = set()
    if booking.buyer and booking.buyer.email:
        recipients.add(booking.buyer.email)
    if booking.agent and booking.agent.email:
        recipients.add(booking.agent.email)

    for email in recipients:
        send_email(
            to=email,
            subject=f"Inspection Report Submitted for Booking #{booking.id}",
            body=f"Dear user,\n\nAn inspection report has been submitted for booking #{booking.id}.\nPlease review and take any necessary action.\n\nThank you."
        )

    flash("Inspection report submitted and both parties notified.", "success")
    return redirect(url_for('agents.agent_bookings'))




def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))
    return R * c

@agents_bp.route('/search-live-agents', methods=['POST'])
def search_live_agents():
    data = request.get_json()
    user_lat = data.get('latitude')
    user_lon = data.get('longitude')

    if user_lat is None or user_lon is None:
        return jsonify([])

    agents = User.query.filter_by(role='agent').filter(
        User.latitude.isnot(None),
        User.longitude.isnot(None)
    ).all()

    results = []
    for agent in agents:
        dist = haversine(user_lat, user_lon, agent.latitude, agent.longitude)
        results.append({
            'id': agent.id,
            'name': f"{agent.first_name} {agent.last_name}",
            'state': agent.state,
            'city': agent.city,
            'distance_km': round(dist, 2),
            'is_online': agent.is_online
        })

    results.sort(key=lambda x: x['distance_km'])
    return jsonify(results)


from sqlalchemy.sql import func
from datetime import datetime, timedelta

@agents_bp.route("/search-agents")
@login_required
def search_agents():
    product_id = request.args.get("product_id", type=int)
    role = request.args.get("role", default="agent")  # 'agent' or 'logistics'

    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("main.home"))

    state = product.state
    city = product.city

    # Get all agents or logistics in that location
    agents = User.query.filter_by(role=role, state=state, city=city).all()

    enriched_agents = []
    for agent in agents:
        avg_rating = db.session.query(func.avg(Review.rating)).filter_by(reviewee_id=agent.id).scalar() or 0
        review_count = db.session.query(Review).filter_by(reviewee_id=agent.id).count()
        online = agent.last_seen and (datetime.utcnow() - agent.last_seen) < timedelta(minutes=5)

        enriched_agents.append({
            "id": agent.id,
            "full_name": f"{agent.first_name} {agent.last_name}",
            "phone": agent.phone,
            "photo": agent.profile_photo,
            "state": agent.state,
            "city": agent.city,
            "online": online,
            "avg_rating": round(avg_rating, 1),
            "review_count": review_count,
            "whatsapp_link": f"https://wa.me/{agent.phone}",
            "specialization": getattr(agent, "specialization", ""),  # if you added this field
        })

    return render_template(
        "search_agents.html",
        agents=enriched_agents,
        product=product,
        user=current_user,role=role
    )

@agents_bp.route('/book-agent', methods=['POST'])
@login_required
def book_agent_post():
    agent_id = request.form.get('agent_id')
    product_id = request.form.get('product_id')
    message = request.form.get('message')

    if not agent_id or not product_id:
        flash("Missing agent or product information.", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    product = Product.query.get(product_id)
    if not product:
        flash("Missing product reference for booking.", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    booking = BookingRequest(
        buyer_id=current_user.id,
        seller_id=product.user_id,
        agent_id=agent_id,
        product_id=product_id,
        message=message,
        status='pending',
        created_at=datetime.utcnow()
    )
    db.session.add(booking)
    db.session.commit()

    flash("Booking request sent to agent successfully!", "success")
    return redirect(url_for('seller_dashboard.product_detail', product_id=product.id))



@agents_bp.route('/agents/details/<int:agent_id>')
def get_agent_details(agent_id):
    agent = User.query.get_or_404(agent_id)
    return render_template('agent_details_popup.html', agent=agent)

@agents_bp.route('/search-live-logistics', methods=['POST'])
def search_nearby_logistics():
    data = request.get_json()
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    # If coordinates are missing, return empty list
    if latitude is None or longitude is None:
        return jsonify([])

    # Fetch all logistics users
    logistics_users = User.query.filter_by(role='logistics').all()

    results = []

    for user in logistics_users:
        print(f'➡️ Checking user: {user.id} - {user.first_name} - lat: {user.latitude}, lon: {user.longitude}')

        if user.latitude is not None and user.longitude is not None:
            distance = haversine(latitude, longitude, user.latitude, user.longitude)
            print(f'✅ Distance to user {user.id}: {distance:.2f} km')

            results.append({
                'id': user.id,
                'name': f"{user.first_name} {user.last_name or ''}",
                'city': user.city,
                'state': user.state,
                'phone': user.phone,
                'email': user.email,
                'avg_rating': getattr(user, 'get_average_rating', lambda: 0)(),
                'review_count': getattr(user, 'get_review_count', lambda: 0)(),
                'specialty': getattr(user, 'specialty', 'Logistics'),
                'about': getattr(user, 'about', 'No info provided'),
                'is_online': getattr(user, 'is_online', False),
                'distance_km': distance
            })

    # Sort results by distance and return
    sorted_results = sorted(results, key=lambda x: x['distance_km'])
    return jsonify(sorted_results)



from flask import request, jsonify
from flask_login import login_required, current_user
from app.realtime_locations import update_user_location

@agents_bp.route("/api/update-location", methods=["POST"])
@login_required
def update_location():
    data = request.json
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    role = current_user.role

    if latitude is None or longitude is None:
        return jsonify({"error": "Missing coordinates"}), 400

    update_user_location(current_user.id, role, latitude, longitude)
    return jsonify({"status": "ok"})

from app.realtime_locations import get_nearby_users

@agents_bp.route("/api/nearby-users")
@login_required
def nearby_users():
    latitude = request.args.get("latitude", type=float)
    longitude = request.args.get("longitude", type=float)
    role = request.args.get("role", default="agent")

    if latitude is None or longitude is None:
        return jsonify({"error": "Missing coordinates"}), 400

    users = get_nearby_users(role, latitude, longitude, radius_km=10)
    enriched = []
    for u in users:
        user_obj = User.query.get(u["user_id"])
        enriched.append({
            "id": user_obj.id,
            "full_name": f"{user_obj.first_name} {user_obj.last_name}",
            "phone": user_obj.phone,
            "photo": user_obj.profile_photo,
            "latitude": u["latitude"],
            "longitude": u["longitude"],
            "role": user_obj.role
        })
    return jsonify(enriched)