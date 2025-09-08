from flask import Blueprint, request, jsonify, render_template,abort, flash, url_for,current_app, redirect, session
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db,  User,LogisticsProfile,AgentKYC,LogisticsBooking,Review,WalletTransaction,EscrowPayment,Wallet,BookingRequest,Product,Notification, Message
from flask_login import login_required, current_user
from datetime import  datetime, timedelta
from app.utils.email_utils import send_email,mail
from werkzeug.utils import secure_filename
from app.utils.payout_utils import get_or_create_wallet
from app.forms import WithdrawalForm
from decimal import Decimal
from app import db
from app.models import Wallet, BankDetails, Withdrawal   # models
from app.forms import WithdrawalForm
import  os
logistics_bp = Blueprint('logistics', __name__, url_prefix='/logistics')
from sqlalchemy.orm import joinedload

from flask_login import login_required, current_user
from sqlalchemy import func

@logistics_bp.route('/dashboard')
@login_required
def logistics_dashboard():
    user = current_user
    page = request.args.get('page', 1, type=int)

    # --- Bookings ---
    total_bookings = LogisticsBooking.query.filter_by(logistics_id=user.id).count()
    completed_bookings = LogisticsBooking.query.filter_by(
        logistics_id=user.id, status='completed'
    ).count()
    pending_bookings = LogisticsBooking.query.filter_by(
        logistics_id=user.id, status='pending'
    ).count()
    recent_bookings = LogisticsBooking.query.filter_by(logistics_id=user.id)

    # --- Revenue Summary (Escrow + Direct) ---
    all_escrows = EscrowPayment.query.filter(
        EscrowPayment.provider_id == user.id,
        EscrowPayment.type.in_(['agent', 'logistics'])
    ).all()

    total_escrow_released = sum(e.base_amount for e in all_escrows if e.status == "released")
    total_escrow_pending = sum(e.base_amount for e in all_escrows if e.status != "released")

    # Direct payments from WalletTransaction
    total_direct_received = db.session.query(func.sum(WalletTransaction.amount)) \
        .filter(
            WalletTransaction.user_id == user.id,
            WalletTransaction.transaction_type == 'credit',
            WalletTransaction.description.like('Received direct payment%'),
            WalletTransaction.status == 'success'
        ).scalar() or 0

    total_earned = total_escrow_released + total_direct_received
    pending_payment = total_escrow_pending  # no pending for direct

    # --- Recent 5 Escrows (keep full objects) ---
    recent_escrows = EscrowPayment.query.filter(
        EscrowPayment.provider_id == user.id,
        EscrowPayment.type == 'logistics'
    ).order_by(EscrowPayment.created_at.desc()).limit(5).all()

    # --- Ratings / Feedback ---
    average_rating = db.session.query(func.avg(Review.rating)) \
        .filter_by(reviewee_id=user.id).scalar()
    average_rating = round(average_rating or 0, 1)

    recent_feedback = Review.query.filter_by(reviewee_id=user.id) \
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

    # --- Notifications ---
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.timestamp.desc()).all()
    unread_count = len(notifications)

    # --- Bookings pagination ---
    bookings_query = LogisticsBooking.query.filter(
        LogisticsBooking.logistics_id == current_user.id,
        LogisticsBooking.status.in_(['pending', 'accepted', 'completed'])
    ).order_by(LogisticsBooking.created_at.desc())
    bookings = bookings_query.paginate(page=page, per_page=10)

    # --- Wallet ---
    wallet = get_or_create_wallet(user_id=user.id)

    # --- Return render ---
    return render_template(
        'logistics/dashboard.html',
        user=user,
        total_bookings=total_bookings,
        completed_bookings=completed_bookings,
        pending_bookings=pending_bookings,
        recent_bookings=recent_bookings,
        total_earned=total_earned,
        pending_payment=pending_payment,
        escrows=recent_escrows,   # 👈 pass full objects, not dicts
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
        logistics=user,
        completion=current_user.profile_completion()
    )



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



@logistics_bp.route('/contact')
def contact():
    return render_template('support/contact.html')


@logistics_bp.route('/notifications')
@login_required
def logistics_notifications():
    # ✅ Query the real DB notifications for the logged-in user
    notifications = Notification.query.filter_by(user_id=current_user.id) \
        .order_by(Notification.timestamp.desc()) \
        .all()

    return render_template('notifications.html', notifications=notifications)


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
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        address = request.form.get('address')
        document_type = request.form.get('document_type')
        files = request.files.getlist('documents')

        if not full_name or not address or not document_type:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('agents.kyc'))

        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        if not upload_folder:
            flash('Upload folder is not configured.', 'danger')
            return redirect(url_for('agents.kyc'))

        document_paths = []
        for file in files:
            if file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                # Save relative path to DB
                document_paths.append(os.path.join('app', 'static', 'uploads', filename))

        # Save KYC to DB
        kyc = AgentKYC(
            user_id=current_user.id,
            full_name=full_name,
            address=address,
            document_type=document_type,
            document_images=document_paths,
            status='pending'
        )
        db.session.add(kyc)
        db.session.commit()
        flash('KYC submitted successfully! Pending admin approval.', 'success')
        return redirect(url_for('logistics.logistics_dashboard'))

    return render_template('logistics/kyc.html')



UPLOAD_FOLDER = "app/static/uploads/profile_photos"

UPLOAD_FOLDER = os.path.join("app", "static", "uploads", "profile_photos")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Ensure directory exists
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

from flask import flash, redirect, url_for

@logistics_bp.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    user = current_user

    if request.method == "POST":
        try:
            user.first_name = request.form.get("first_name")
            user.last_name = request.form.get("last_name")
            user.phone = request.form.get("phone")
            user.state = request.form.get("state")
            user.city = request.form.get("city")
            user.street = request.form.get("street")
            user.company_name = request.form.get("company_name")
            user.about = request.form.get("about")

            if "profile_photo" in request.files:
                file = request.files["profile_photo"]
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join("app/static/uploads", filename))
                    user.profile_photo = f"uploads/{filename}"

            db.session.commit()
            flash("✅ Profile updated successfully!", "success")
            return redirect(url_for("logistics.edit_profile"))

        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error updating profile: {str(e)}", "danger")

    return render_template("logistics/edit_profile.html", user=user)



UPLOAD_FOLDER = os.path.join(os.getcwd(), "app", "static", "uploads")

@logistics_bp.before_app_request
def setup_upload_folder():
    current_app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)

# app/agents/routes.py
# app/agents/routes.py
@logistics_bp.route('/upload-documents', methods=['GET', 'POST'])
@login_required
def upload_documents():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        address = request.form.get("address")
        doc_type = request.form.get("doc_type")  # required
        files = request.files.getlist("documents")  # optional multiple files

        if not doc_type:
            flash("You must select a document type", "danger")
            return redirect(request.url)

        saved_files = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
                saved_files.append(filename)

        flash("Documents uploaded successfully!", "success")
        return redirect(url_for("logistics.upload_documents"))

    return render_template("upload_documents.html")

@logistics_bp.route('/delete-document/<int:index>', methods=['POST'])
@login_required
def delete_document(index):
    documents = current_user.documents or []
    if 0 <= index < len(documents):
        try:
            # Delete file from disk
            filepath = documents.pop(index)
            if os.path.exists(filepath):
                os.remove(filepath)

            current_user.documents = documents
            db.session.commit()
            flash("Document deleted successfully.", "success")
        except Exception as e:
            db.session.rollback()
            flash("Failed to delete document.", "danger")
            print("Document deletion error:", e)
    else:
        flash("Invalid document.", "warning")
    return redirect(url_for('logistics.upload_documents'))

@logistics_bp.route('/logistic_profile_standalone/<int:user_id>')
@login_required
def logistic_profile_standalone(user_id):
    # Fetch logistics user
    logistic = User.query.filter_by(id=user_id, role='logistics').first()
    if not logistic:
        abort(404, description="Logistics provider not found")

    # Optional: get existing booking if needed
    booking = BookingRequest.query.filter_by(agent_id=user_id, buyer_id=current_user.id).first()

    # Get reviews for this logistic provider
    reviews = (
        Review.query
        .join(Review.booking)
        .filter(BookingRequest.agent_id == user_id)
        .options(joinedload(Review.reviewer))
        .all()
    )

    positive_reviews = [r for r in reviews if r.rating >= 4]
    negative_reviews = [r for r in reviews if r.rating <= 2]
    average_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0
    total_reviews = len(reviews)

    # Return only modal content if called via AJAX/modal
    if request.args.get('modal'):
        return render_template(
            'logistics/logistic_profile_modal.html',
            logistic=logistic,
            booking=booking,
            positive_reviews=positive_reviews,
            negative_reviews=negative_reviews,
            average_rating=average_rating,
            total_reviews=total_reviews
        )

    # Otherwise return full page
    return render_template('logistics/logistic_profile.html', logistic=logistic)

@logistics_bp.route("/withdraw", methods=["GET", "POST"])
@login_required
def logistics_withdraw():
    # ✅ Only logistics allowed
    if current_user.role != "logistics":
        flash("Access denied.", "danger")
        return redirect(url_for("logistics.dashboard"))

    # ✅ Get or create wallet
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    if not wallet:
        wallet = Wallet(
            user_id=current_user.id,
            balance=Decimal("0.00"),
            pending_balance=Decimal("0.00")
        )
        db.session.add(wallet)
        db.session.commit()

    form = WithdrawalForm()

    # ✅ Load saved bank accounts
    bank_accounts = BankDetails.query.filter_by(user_id=current_user.id).all()
    form.bank_account.choices = [(b.id, f"{b.bank_name} - {b.account_number}") for b in bank_accounts]

    if request.method == "POST" and form.validate_on_submit():
        selected_bank = BankDetails.query.get(form.bank_account.data)
        amount = Decimal(str(form.amount.data))

        if not selected_bank:
            flash("Selected bank not found.", "danger")
            return redirect(url_for("logistics.logistics_withdraw"))

        if amount > (wallet.balance or Decimal("0.00")):
            flash("Insufficient balance.", "danger")
            return redirect(url_for("logistics.logistics_withdraw"))

        # ✅ Move balance → pending
        wallet.balance = (wallet.balance or Decimal("0.00")) - amount
        wallet.pending_balance = (wallet.pending_balance or Decimal("0.00")) + amount

        # ✅ Create withdrawal request for admin approval
        withdrawal = Withdrawal(
            user_id=current_user.id,
            bank_id=selected_bank.id,
            amount=amount,
            status="pending"
        )

        db.session.add(withdrawal)
        db.session.add(wallet)
        db.session.commit()
        db.session.refresh(wallet)

        flash(f"Withdrawal of ₦{amount:,.2f} submitted. Awaiting admin approval.", "success")
        return redirect(url_for("logistics.logistics_dashboard"))

    return render_template(
        "wallet/logistics_withdraw.html",
        form=form,
        wallet=wallet,
        bank_accounts=bank_accounts
    )
