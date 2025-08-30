import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash,session, jsonify, current_app
from werkzeug.utils import secure_filename
from app.notifications.events import notify_agent_inspection_marked_complete
from app.utils.subscription_utils import get_upload_limit  # ✅ Make sure this exists
from app.utils.paystack import verify_paystack_payment,get_escrow_role_field  # ✅ Ensure this exists too
from app.utils.paystack import initialize_transaction
from app.utils. payout_utils import initiate_paystack_transfer
from app.utils.payout_utils import get_or_create_wallet,to_decimal
from flask_socketio import SocketIO, emit, join_room, leave_room
from app.utils.email import send_email  # adjust path based on where send_email is defined
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
from app.routes.utils import generate_reference
from decimal import Decimal
from app.extensions import db, mail, socketio
from flask_mail import Message
from app.models import BookingRequest, User,Product
#from app.utils import send_async_emailagent, subscription_utilis
from flask import current_app, abort
from threading import Thread
from app.notifications.email import send_email_to_agent
from sqlalchemy import not_, or_
#from app.routes.utils import send_email_to_agent_on_booking,EscrowPayment,EscrowPayment

from app.forms import BookProductForm  # make sure this is correct

from app.extensions import csrf
import csv
from flask import make_response
from datetime import datetime, timedelta
from app.extensions import db
from decimal import Decimal, InvalidOperation
import os
from app.models import BookingRequest
from app.utils.subscription_utils import get_upload_limit
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from app.models import User, Product, Review, Purchase, AgentProfile
from sqlalchemy.sql import func

from flask_login import current_user
from app.models import BookingRequest, Notification
from app.extensions import db
from app.models import BookingRequest,Wallet,Wishlist,ServiceEscrow,FundTransfer,ProductReview,AdminRevenue,Order,WalletTransaction, InspectionFeedback,SubscriptionPlan,PayoutTransaction
from app.forms import FeedbackForm,EscrowPaymentForm,PayoutForm,BankDetailsForm,WithdrawalForm,CreateOrderForm
from app.utils.paystack import (create_transfer_recipient,verify_account_number,
                                get_banks_from_paystack,create_recipient_code,resolve_account_name,get_banks_from_api)
from app.utils.subscription_utils import handle_booking_payment
from app.models import Subscription
import requests
from app.utils.promotion import get_price_for_promo


# app/seller_dashboard/routes.py or similar
seller_dashboard_bp = Blueprint('seller_dashboard', __name__, url_prefix='/dashboard')


PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

from flask_login import current_user
from app.models import Product, BookingRequest, Notification,Inspection,Escrow,BankDetails, PaymentStatus, OrderStatus, StatusEnum, PaymentStatus, OrderStatus, StatusEnum
from flask import render_template
from flask_login import login_required

from sqlalchemy import func, and_

from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import func, or_



from datetime import datetime, timedelta
from sqlalchemy import func


from decimal import Decimal
from decimal import Decimal, ROUND_DOWN


from decimal import Decimal, ROUND_DOWN

def to_decimal(value):
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

@seller_dashboard_bp.route('/my-dashboard')
@login_required
def my_dashboard():
    user = current_user

    # --- Wallet & Escrow ---
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    balance = to_decimal(wallet.balance if wallet else 0)

    # Buyer escrows
    buyer_escrows = EscrowPayment.query.filter_by(buyer_id=user.id)\
        .order_by(EscrowPayment.created_at.desc()).limit(5).all()
    buyer_locked_total = sum(
        to_decimal(e.total_amount) for e in buyer_escrows if e.status in ['paid', 'locked'] and not e.is_released
    )
    paid_escrow_total = to_decimal(
        db.session.query(func.coalesce(func.sum(EscrowPayment.total_amount), 0))\
        .filter(EscrowPayment.buyer_id==user.id, EscrowPayment.status.in_(['locked','completed'])).scalar()
    )

    # Seller escrows
    seller_escrows = EscrowPayment.query.filter_by(provider_id=user.id)\
        .order_by(EscrowPayment.created_at.desc()).limit(5).all()
    locked_escrow_total = sum(
        to_decimal(e.total_amount) for e in seller_escrows if e.status in ['paid','locked'] and not e.is_released
    )

    # Released / Withdrawn amounts
    released_amount = to_decimal(
        db.session.query(func.coalesce(func.sum(EscrowPayment.total_amount), 0))\
        .filter(
            EscrowPayment.is_released==True,
            EscrowPayment.is_withdrawn==False,
            ((EscrowPayment.buyer_id==user.id)|(EscrowPayment.provider_id==user.id))
        ).scalar()
    )
    withdrawn_amount = to_decimal(
        db.session.query(func.coalesce(func.sum(EscrowPayment.total_amount), 0))\
        .filter(
            EscrowPayment.is_withdrawn==True,
            ((EscrowPayment.buyer_id==user.id)|(EscrowPayment.provider_id==user.id))
        ).scalar()
    )

    # --- Orders Summary ---
    total_orders = Order.query.filter(
        (Order.buyer_id == user.id) | (Order.seller_id == user.id)
    ).count()
    pending_orders = Order.query.filter(
        ((Order.buyer_id == user.id) | (Order.seller_id == user.id)) &
        (Order.status == 'pending')
    ).count()
    completed_orders = Order.query.filter(
        ((Order.buyer_id == user.id) | (Order.seller_id == user.id)) &
        (Order.status == 'completed')
    ).count()
    sales_progress = round((completed_orders / total_orders * 100) if total_orders else 0, 2)
    released_percent = round(
        float(released_amount / (locked_escrow_total + released_amount) * 100) if (locked_escrow_total + released_amount) > 0 else 0, 2
    )

    # --- Recipients for Transfer ---
    recipients = {
        'seller': User.query.filter_by(role='seller').all(),
        'agent': User.query.filter_by(role='agent').all(),
        'logistics': User.query.filter_by(role='logistics').all(),
        'vet': User.query.filter_by(role='vet').all()
    }

    # --- Products ---
    products = Product.query.filter_by(user_id=user.id, is_deleted=False).all()
    for product in products:
        product.sales_count = Order.query.filter_by(product_id=product.id, status='completed').count()
    top_products = sorted(products, key=lambda p: p.sales_count, reverse=True)[:5]

    # --- Mini Profile ---
    mini_profile = {
        'full_name': f"{user.first_name} {user.last_name}",
        'role': user.role,
        'email': user.email,
    }

    # --- Escrow Summary (Buyer / Seller) ---
    escrows = EscrowPayment.query.filter(EscrowPayment.buyer_id==user.id)\
        .order_by(EscrowPayment.created_at.desc()).all()

    service_escrows = EscrowPayment.query.filter(
        EscrowPayment.buyer_id==user.id,
        EscrowPayment.type.in_(["agent","logistics"])
    ).order_by(EscrowPayment.created_at.desc()).limit(5).all()

    total_released = sum(to_decimal(e.partial_release_amount) for e in escrows)
    total_pending = sum(to_decimal(e.total_amount) - to_decimal(e.partial_release_amount) for e in escrows)
    progress_percent = float(total_released / (total_released + total_pending) * 100) if (total_released + total_pending) > 0 else 0

    return render_template(
        'dashboard.html',
        user=user,
        service_escrows=service_escrows,
        escrows=escrows,
        total_released=total_released,
        total_pending=total_pending,
        progress_percent=progress_percent,
        mini_profile=mini_profile,
        balance=balance,
        buyer_escrows=buyer_escrows,
        seller_escrows=seller_escrows,
        buyer_locked_total=buyer_locked_total,
        paid_escrow_total=paid_escrow_total,
        locked_escrow_total=locked_escrow_total,
        released_amount=released_amount,
        withdrawn_amount=withdrawn_amount,
        total_orders=total_orders,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        sales_progress=sales_progress,
        released_percent=released_percent,
        recipients=recipients,
        products=products,
        top_products=top_products,

        timedelta=timedelta
    )

@seller_dashboard_bp.context_processor
def inject_now():
    return {'now': datetime.utcnow}
@seller_dashboard_bp.route('/upload_product', methods=['GET', 'POST'])
@login_required
def upload_product():
    # ✅ Reload the latest user data from DB
    user = User.query.get(current_user.id)

    # ✅ Define plan limits
    plan_limits = {
        'Free': 2,
        'Starter': 5,
        'Pro': 10,
        'Premium': 100
    }

    plan_name = (user.plan_name or 'Free').capitalize()
    upload_limit = plan_limits.get(plan_name, 2)

    # ✅ Count products
    uploaded_count = Product.query.filter_by(user_id=user.id, is_deleted=False).count()

    if uploaded_count >= upload_limit:
        flash(f"Upload limit reached ({upload_limit}) for your {plan_name} plan. Please upgrade.", "danger")
        return redirect(url_for('seller_dashboard.upgrade_plan'))

    # ✅ If within limit, handle form

    if request.method == 'POST':
        # Get form fields
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        type_ = request.form.get('type', '').strip()
        state = request.form.get('state', '').strip()
        city = request.form.get('city', '').strip()
        description = request.form.get('description', '').strip()
        open_to_negotiation_raw = request.form.get('open_to_negotiation')
        images = request.files.getlist('images')

        # Normalize open_to_negotiation to enum strings: 'yes', 'no', 'not sure'
        if open_to_negotiation_raw:
            val = open_to_negotiation_raw.lower()
            if val in ['true', 'yes', '1', 'on']:
                open_to_negotiation = 'yes'
            elif val in ['false', 'no', '0', 'off']:
                open_to_negotiation = 'no'
            else:
                open_to_negotiation = 'not sure'
        else:
            open_to_negotiation = 'not sure'

        # Validate quantity and price
        try:
            quantity = int(request.form.get('quantity', '0'))
            price = float(request.form.get('price', '0'))
        except ValueError:
            flash("❌ Quantity and Price must be valid numbers.", "danger")
            return redirect(url_for('seller_dashboard.upload_product'))

        # Validate required fields
        if not all([title, category, type_, state, city, description]) or quantity <= 0 or price <= 0:
            flash("❌ All fields are required and quantity/price must be greater than zero.", "danger")
            return redirect(url_for('seller_dashboard.upload_product'))

        if len(images) < 3:
            flash("📸 Please upload at least 3 product images.", "warning")
            return redirect(url_for('seller_dashboard.upload_product'))

        # Image upload folder
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)

        image_paths = []
        for image in images[:5]:  # Limit max 5 images
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                unique_name = f"{uuid.uuid4()}_{filename}"
                save_path = os.path.join(upload_folder, unique_name)
                image.save(save_path)
                image_paths.append(f'uploads/{unique_name}')
            else:
                flash("❌ Only jpg, png, gif, webp files are allowed.", "danger")
                return redirect(url_for('seller_dashboard.upload_product'))

        # Boost & feature based on plan
        is_featured = plan_name in ['Pro', 'Premium']
        boost_score = {'Free': 0, 'Starter': 1, 'Pro': 5, 'Premium': 10}.get(plan_name, 0)

        # Save product to database
        product = Product(
            user_id=user.id,
            title=title,
            category=category,
            type=type_,
            latitude=user.latitude,
            longitude=user.longitude,
            state=state,
            city=city,
            quantity=quantity,
            description=description,
            price=price,
            open_to_negotiation=open_to_negotiation,
            phone_display=user.phone,
            photos=image_paths,
            is_featured=is_featured,
            boost_score=boost_score
        )
        db.session.add(product)
        db.session.commit()

        flash("✅ Product uploaded successfully!", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    return render_template('upload_product.html', user=user)




@seller_dashboard_bp.route('/edit-product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    if product.user_id != current_user.id:
        flash("Unauthorized edit attempt.", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    if request.method == 'POST':
        product.title = request.form.get('title')
        product.type = request.form.get('type')
        product.state = request.form.get('state')
        product.city = request.form.get('city')
        product.quantity = request.form.get('quantity')
        product.price = request.form.get('price')
        product.category = request.form.get('category')
        product.open_to_negotiation = request.form.get('open_to_negotiation')

        photos = request.files.getlist('photos')
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        if product.photos is None:
            product.photos = []

        for file in photos:
            if file and allowed_file(file.filename):
                filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                rel_path = f"uploads/{filename}"
                if rel_path not in product.photos:
                    product.photos.append(rel_path)

        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    return render_template('edit_product.html', product=product, getattr=getattr, now=datetime.utcnow())

@seller_dashboard_bp.route('/delete-product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)

    if product.user_id != current_user.id:
        flash("Unauthorized delete attempt.", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    product.is_deleted = True
    db.session.commit()
    flash('Product deleted.', 'info')
    return redirect(url_for('seller_dashboard.my_dashboard'))

@seller_dashboard_bp.route("/agents")
@login_required
def view_agents():
    agents = User.query.filter_by(role="agent").all()
    return render_template("search/agents.html", agents=agents)

@seller_dashboard_bp.route('/view-vets')
@login_required
def view_vets():
    return render_template('vets.html')

@seller_dashboard_bp.route('/view-logistics')
@login_required
def view_logistics():
    return render_template('logistics.html')


@seller_dashboard_bp.route('/search-agents')
def search_agents():
    from app.models import Agent, User  # ensure models are imported

    specialization = request.args.get('specialization')
    state = request.args.get('state')
    city = request.args.get('city')
    verified = request.args.get('verified') == 'true'
    availability = request.args.get('availability')
    min_rating = request.args.get('min_rating', type=float)

    query = Agent.query.join(User).filter(User.role == 'agent')

    if specialization:
        query = query.filter(Agent.specialization.ilike(f'%{specialization}%'))
    if state:
        query = query.filter(User.state == state)
    if city:
        query = query.filter(User.city == city)
    if verified:
        query = query.filter(Agent.is_verified.is_(True))
    if availability:
        query = query.filter(Agent.availability == availability)
    if min_rating:
        query = query.filter(Agent.rating >= min_rating)

    agents = query.all()

    # 📝 Replace with real state list or pull from DB
    states = ['Lagos', 'Abuja', 'Kaduna', 'Kano', 'Enugu', 'Rivers']

    return render_template('search_agents.html', agents=agents, states=states)


@seller_dashboard_bp.route('/search/logistics')
@login_required
def search_logistics():
    state = request.args.get('state')
    city = request.args.get('city')
    query = db.session.query(User).filter(User.role == 'logistics')

    if state:
        query = query.filter(User.state == state)
    if city:
        query = query.filter(User.city == city)

    logistics = query.all()
    return render_template('search/logistics.html', logistics=logistics, state=state, city=city)

@seller_dashboard_bp.route('/search/vets')
@login_required
def search_vets():
    state = request.args.get('state')
    city = request.args.get('city')
    query = db.session.query(User).filter(User.role == 'vet')

    if state:
        query = query.filter(User.state == state)
    if city:
        query = query.filter(User.city == city)

    vets = query.all()
    return render_template('search/vets.html', vets=vets, state=state, city=city)

@seller_dashboard_bp.route("/api/search-agents")
def search_agents_api():
    query = request.args.get("q", "").lower()
    agents = User.query.filter(User.role == "agent").all()

    filtered = []
    for a in agents:
        if query in a.first_name.lower() or query in a.last_name.lower() or query in a.state.lower() or query in a.city.lower():
            filtered.append({
                "first_name": a.first_name,
                "last_name": a.last_name,
                "phone": a.phone,
                "state": a.state,
                "city": a.city,
                "chat_url": url_for('chat.chat_page', receiver_id=a.id)
            })

    return jsonify(filtered)


@seller_dashboard_bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        fields = ['first_name', 'last_name', 'email', 'phone', 'state', 'city', 'street', 'company_name', 'about']
        for field in fields:
            val = request.form.get(field)
            if val is not None:
                setattr(current_user, field, val.strip())

        # Profile photo upload
        photo = request.files.get('profile_photo')
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
            os.makedirs(folder, exist_ok=True)
            filepath = os.path.join(folder, filename)
            photo.save(filepath)
            current_user.profile_photo = f'/static/uploads/profiles/{filename}'

        try:
            db.session.add(current_user)  # ⬅️ Force SQLAlchemy to track update
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile: ' + str(e), 'danger')

        return redirect(url_for('seller_dashboard.view_profile', user_id=current_user.id))

    return render_template('edit_profile.html', user=current_user)


from datetime import datetime

# ✅ View profile route (unchanged)
@seller_dashboard_bp.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    user = User.query.get_or_404(user_id)
    return render_template('view_profile.html', user=user)

# ✅ Product detail route with agents
from sqlalchemy import or_

@seller_dashboard_bp.route("/product/<int:product_id>")
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    seller = User.query.get(product.user_id)

    # Assigned agent
    agent = User.query.get(product.agent_id) if product.agent_id else None

    # Reviews for the agent
    reviews, average_rating, total_reviews = [], 0, 0
    positive_reviews, neutral_reviews, negative_reviews = [], [], []

    if agent:
        # Join Review → BookingRequest → filter by agent_id
        reviews = db.session.query(Review).join(BookingRequest).filter(
            BookingRequest.agent_id == agent.id
        ).order_by(Review.created_at.desc()).options(
            joinedload(Review.reviewer)
        ).all()

        average_rating = db.session.query(func.avg(Review.rating)).join(BookingRequest).filter(
            BookingRequest.agent_id == agent.id
        ).scalar() or 0

        total_reviews = len(reviews)
        positive_reviews = [r for r in reviews if r.rating >= 4]
        neutral_reviews = [r for r in reviews if r.rating == 3]
        negative_reviews = [r for r in reviews if r.rating <= 2]



    # Increment product views
    product.views = (product.views or 0) + 1
    db.session.commit()

    # Similar products in same category but not current one
    similar_products = Product.query.filter(
        Product.category == product.category,
        Product.id != product.id,
        Product.is_deleted == False
    ).limit(4).all()

    # Nearby agents in same state and city
    agents_in_state = User.query.filter(
        User.role == 'agent',
        func.lower(User.state) == func.lower(product.state)
    ).all()

    nearby_agents = sorted(
        agents_in_state,
        key=lambda a: 0 if a.city.lower() == product.city.lower() else 1
    )

    # Product reviews by buyers
    product_reviews = ProductReview.query.filter_by(
        product_id=product.id
    ).order_by(ProductReview.created_at.desc()).all()

    product_average_rating = db.session.query(func.avg(ProductReview.rating)).filter_by(
        product_id=product.id
    ).scalar() or 0

    product_total_reviews = len(product_reviews)

    # Prevent duplicate product review
    existing_review = ProductReview.query.filter_by(
        product_id=product.id,
        reviewer_id=current_user.id
    ).first()

    if existing_review:
        flash("You have already submitted a review for this product.", "warning")
        return redirect(url_for('seller_dashboard.product_detail', product_id=product.id))

    # Random agents in different states
    random_agents = User.query.filter(
        User.role == 'agent',
        func.lower(User.state) != func.lower(product.state)
    ).order_by(func.random()).limit(4).all()

    # fetch reviews linked to orders for this product
    reviews = (
        Review.query.join(Order)
        .filter(Order.product_id == product.id, Review.order_id != None)
        .all()
    )
    reviews = product.reviews
    total_reviews = len(reviews)

    if total_reviews > 0:
        avg_rating = sum(r.rating for r in reviews) / total_reviews
    else:
        avg_rating = 0

    avg_rating_rounded = round(avg_rating, 1)

    return render_template(
        'product_detail.html',
        product=product,
        product_id=product_id,
        seller=seller,
        agent=agent,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        avg_rating_rounded=avg_rating_rounded,
        similar_products=similar_products,
        nearby_agents=nearby_agents,
        random_agents=random_agents,
        reviews=reviews,
        positive_reviews=positive_reviews,
        neutral_reviews=neutral_reviews,
        negative_reviews=negative_reviews,
    )


@seller_dashboard_bp.route('/report-product/<int:product_id>', methods=['POST'])
@login_required
def report_product(product_id):
    # Implement logic to handle report (e.g., store in DB or flag it)
    flash("Thank you for reporting this product.", "info")
    return redirect(url_for('seller_dashboard.product_detail', product_id=product_id))


@seller_dashboard_bp.route('/delete-photo/<int:product_id>/<path:photo_path>', methods=['POST'])
@login_required
def delete_photo(product_id, photo_path):
    product = Product.query.get_or_404(product_id)

    if product.user_id != current_user.id:
        flash("Unauthorized attempt.", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    # Remove photo from the list
    photo_to_delete = photo_path.replace("..", "")  # Prevent directory traversal
    if photo_to_delete in product.photos:
        product.photos.remove(photo_to_delete)

        # Delete the actual file from disk
        full_path = os.path.join(current_app.root_path, 'static', photo_to_delete)
        if os.path.exists(full_path):
            os.remove(full_path)

        db.session.commit()
        flash("Photo deleted.", "info")
    else:
        flash("Photo not found.", "warning")

    return redirect(url_for('seller_dashboard.edit_product', product_id=product.id))

@seller_dashboard_bp.route('/book-agent/<int:agent_id>/<int:product_id>', methods=['GET', 'POST'])
@login_required
def book_agent(agent_id, product_id):
    agent = User.query.get_or_404(agent_id)
    product = Product.query.get_or_404(product_id)



    if request.method == 'POST':
        date = request.form['date']
        time = request.form['time']
        reason = request.form['reason']

        booking = BookingRequest(
            buyer_id=current_user.id,
            agent_id=agent.id,
            seller_id=product.user_id,  # ✅ ensure this prints a value
            product_id=product.id,
            date=date,
            time=time,
            reason=reason,
            status='pending',
            booking_time=datetime.utcnow()
        )
        db.session.add(booking)
        db.session.commit()

        flash('Booking submitted to agent!', 'success')
        return redirect(url_for('seller_dashboard.dashboard_home'))

    return render_template('book_agent.html', agent=agent, product=product)



@seller_dashboard_bp.route('/notifications')
@login_required
def notifications():
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()

    # Mark them as read
    for note in notes:
        note.is_read = True
    db.session.commit()

    return render_template('notifications.html', notifications=notes)


@seller_dashboard_bp.route("/mark-inspection/<int:booking_id>", methods=["POST"])
@login_required
def mark_inspection(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)
    if booking.buyer_id != current_user.id:
        abort(403)

    booking.inspection_seen_by_buyer = True
    if request.form.get("mark") == "complete":
        booking.inspection_marked_complete = True
    else:
        booking.inspection_marked_complete = False

    db.session.commit()
    flash("Inspection status updated.", "success")
    return redirect(url_for("seller_dashboard.view_inspections"))


# routes.py under seller_dashboard_bp

@seller_dashboard_bp.route('/mark-complete/<int:booking_id>', methods=['POST'])
@login_required
def mark_inspection_as_complete(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)

    if booking.buyer_id != current_user.id:
        abort(403)

    booking.inspection_marked_complete = True
    db.session.commit()

    # Notify via Socket.IO
    notify_agent_inspection_marked_complete(booking)

    # Notify via Email
    send_email_to_agent(booking)

    flash('✅ You marked the inspection as complete.', 'success')
    return redirect(url_for('seller_dashboard.my_dashboard'))

@seller_dashboard_bp.route('/inspection-products')
@login_required
def inspection_products():
    bookings = (
        db.session.query(BookingRequest)
        .join(Product, BookingRequest.product_id == Product.id)
        .filter(
            Product.user_id == current_user.id,
            BookingRequest.inspection_reported_at != None,
            BookingRequest.inspection_marked_complete == None
        )
        .order_by(BookingRequest.created_at.desc())
        .all()
    )

    return render_template('inspections.html', bookings=bookings, title="Inspection Products")




@seller_dashboard_bp.route('/pending-inspections')
@login_required
def pending_inspections():
    bookings = (
        db.session.query(BookingRequest)
        .join(Product, BookingRequest.product_id == Product.id)
        .filter(
            Product.user_id == current_user.id,
            BookingRequest.inspection_reported_at != None,
            BookingRequest.inspection_marked_complete == None
        )
        .order_by(BookingRequest.created_at.desc())
        .all()
    )
    return render_template('inspection_list.html', bookings=bookings, title="Pending Confirmation")


def notify_booking_parties(agent_id, buyer_id, product_id=None):
    from app.models import Notification, Product
    from app.extensions import db, socketio

    notifications = []

    agent_note = Notification(
        user_id=agent_id,
        sender_id=buyer_id,
        message="📅 New booking request received!",
        type='booking',
        is_read=False
    )
    db.session.add(agent_note)
    notifications.append((agent_id, agent_note.message))

    if product_id:
        product = Product.query.get(product_id)
        if product and product.user_id != agent_id:
            seller_note = Notification(
                user_id=product.user_id,
                sender_id=buyer_id,
                message="📦 Your product received a booking via an agent.",
                type='booking',
                is_read=False
            )
            db.session.add(seller_note)
            notifications.append((product.user_id, seller_note.message))

    db.session.commit()

    for user_id, message in notifications:
        socketio.emit('new_notification', {
            'message': message,
            'user_id': user_id
        }, room=str(user_id))



@seller_dashboard_bp.route('/book/<int:product_id>', methods=['GET', 'POST'])
@login_required
def book_product(product_id):
    product = Product.query.get_or_404(product_id)
    agent = User.query.get_or_404(product.user_id)
    form = BookProductForm()

    if current_user.id == product.user_id:
        flash("You cannot book your own product.", "warning")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    if form.validate_on_submit():


        booking = BookingRequest(
            buyer_id=current_user.id,
            agent_id=agent.id,
            product_id=product.id,
            date=form.date.data,
            time=form.time.data,
            reason=form.reason.data,
            booking_time=datetime.utcnow(),
            status='pending'
        )
        db.session.add(booking)
        db.session.commit()
        inspection = Inspection(
            booking_id=booking.id,
            inspector_id=agent.id,  # assuming agent is the inspector
            inspection_date=form.date.data,  # or datetime.utcnow()
            status='pending',
            notes=None
        )
        db.session.add(inspection)
        db.session.commit()

        flash("✅ Booking submitted successfully.", "success")
        return redirect(url_for('seller_dashboard.booking_confirmation', booking_id=booking.id))

    return render_template(
        'book_product.html',
        product=product,
        agent=agent,
        form=form
    )
@seller_dashboard_bp.route('/booking-confirmation/<int:booking_id>')
@login_required
def booking_confirmation(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)
    return render_template('booking_confirmation.html', booking=booking)

@seller_dashboard_bp.route('/inspections-list')
@login_required
def inspections_list():
    if current_user.role == 'agent':
        inspections = Inspection.query.filter_by(inspector_id=current_user.id).all()
    else:
        inspections = Inspection.query.join(BookingRequest).filter(
            BookingRequest.buyer_id == current_user.id
        ).all()

    return render_template('inspections.html', inspections=inspections)

from sqlalchemy.orm import joinedload


@seller_dashboard_bp.route('/booking-history', methods=['GET', 'POST'])
@login_required
def booking_history():
    page = request.args.get('page', 1, type=int)

    # Fetch buyer's bookings (most recent first)
    bookings_query = BookingRequest.query.filter_by(buyer_id=current_user.id).order_by(BookingRequest.date.desc())
    bookings = bookings_query.paginate(page=page, per_page=5)

    # Prepare feedback forms for each booking (with prefix for multiple forms)
    feedback_forms = {booking.id: FeedbackForm(prefix=str(booking.id), formdata=request.form if request.method == 'POST' else None)
                      for booking in bookings.items}

    # Handle feedback submission
    if request.method == 'POST':
        booking_id = request.form.get('booking_id')
        if not booking_id:
            flash("Invalid booking.", "danger")
            return redirect(url_for('seller_dashboard.booking_history', page=page))

        booking_id = int(booking_id)
        form = feedback_forms.get(booking_id)
        booking = BookingRequest.query.get(booking_id)
        if not booking or not form:
            flash("Booking not found.", "danger")
            return redirect(url_for('seller_dashboard.booking_history', page=page))

        # Check if feedback already exists
        existing_review = Review.query.filter_by(booking_id=booking_id, reviewer_id=current_user.id).first()
        if existing_review:
            flash("You have already submitted feedback for this booking.", "warning")
            return redirect(url_for('seller_dashboard.booking_history', page=page))

        # Validate form
        if form.validate_on_submit():
            review = Review(
                booking_id=booking.id,
                reviewer_id=current_user.id,
                reviewee_id=booking.agent_id,  # Review is for the agent
                product_id=booking.product_id,
                rating=form.rating.data,
                comment=form.comment.data
            )
            db.session.add(review)

            # Notification for agent
            notif = Notification(
                user_id=booking.agent_id,
                message=f"{current_user.first_name} submitted feedback for booking #{booking.id}"
            )
            db.session.add(notif)
            db.session.commit()

            # Email notification to agent
            agent = User.query.get(booking.agent_id)
            if agent and agent.email:
                msg = Message(
                    subject=f"New Feedback for Booking #{booking.id}",
                    recipients=[agent.email],
                    body=f"Hi {agent.first_name},\n\nYou have received new feedback from {current_user.first_name} {current_user.last_name} for booking #{booking.id}.\n\nPlease log in to your dashboard to view it."
                )
                mail.send(msg)

            flash("Feedback submitted successfully!", "success")
            return redirect(url_for('seller_dashboard.booking_history', page=page))
        else:
            flash("Failed to submit feedback. Please check your inputs.", "danger")
            return redirect(url_for('seller_dashboard.booking_history', page=page))

    return render_template(
        'inspection_history.html',
        bookings=bookings,
        feedback_forms=feedback_forms
    )


@seller_dashboard_bp.route('/inspection/<int:booking_id>/feedback', methods=['GET', 'POST'])
@login_required
def leave_feedback(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)
    if booking.buyer_id != current_user.id:
        flash("You can only leave feedback for your own bookings.", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    form = FeedbackForm()
    if form.validate_on_submit():
        feedback = InspectionFeedback(
            booking_id=booking.id,
            user_id=current_user.id,
            rating=form.rating.data,
            comment=form.comment.data,
            created_at=datetime.utcnow()
        )
        db.session.add(feedback)
        db.session.commit()
        flash("✅ Feedback submitted successfully.", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    return render_template('leave_feedback.html', form=form, booking=booking)

@seller_dashboard_bp.route('/my-feedback')
@login_required
def my_feedback():
    feedback_list = InspectionFeedback.query.join(BookingRequest).filter(
        BookingRequest.agent_id == current_user.id
    ).order_by(InspectionFeedback.created_at.desc()).all()

    # Calculate average
    ratings = [fb.rating for fb in feedback_list if fb.rating]
    average_rating = sum(ratings) / len(ratings) if ratings else None

    return render_template('inspection_feedback.html', feedback_list=feedback_list, average_rating=average_rating)


@seller_dashboard_bp.route('/reply-feedback/<int:feedback_id>', methods=['POST'])
@login_required
def reply_feedback(feedback_id):
    feedback = InspectionFeedback.query.get_or_404(feedback_id)

    if current_user.id != feedback.booking.agent_id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('seller_dashboard.my_feedback'))

    reply = request.form.get('reply')
    feedback.reply = reply
    feedback.replied_at = datetime.utcnow()
    db.session.commit()
    flash("✅ Reply submitted.", "success")
    return redirect(url_for('seller_dashboard.my_feedback'))

@seller_dashboard_bp.route('/delete-feedback/<int:feedback_id>')
@login_required
def delete_feedback(feedback_id):
    feedback = InspectionFeedback.query.get_or_404(feedback_id)
    if feedback.user_id != current_user.id:
        abort(403)

    db.session.delete(feedback)
    db.session.commit()
    flash("🗑 Feedback deleted.", "info")
    return redirect(url_for('seller_dashboard.my_feedback'))


@seller_dashboard_bp.route('/submit-feedback/<int:booking_id>/<int:product_id>/<int:reviewee_id>', methods=['POST'])
@login_required
def submit_feedback(booking_id, product_id, reviewee_id):
    form = FeedbackForm()
    if not form.validate_on_submit():
        flash("Failed to submit feedback. Please check your inputs.", "danger")
        return redirect(url_for('seller_dashboard.booking_history'))
        # Ensure no duplicate review for the same booking
        existing_review = Review.query.filter_by(booking_id=booking_id, reviewer_id=current_user.id).first()
        if existing_review:
            flash("You have already submitted feedback for this booking.", "warning")
            return redirect(url_for('seller_dashboard.booking_history'))

        review = Review(
            booking_id=booking.id,
            reviewer_id=current_user.id,
            reviewee_id=reviewee.id,
            product_id=product.id,
            rating=form.rating.data,
            comment=form.comment.data,
            created_at=datetime.utcnow()
        )

        db.session.add(review)
        db.session.commit()
        flash("Feedback submitted successfully!", "success")
        return redirect(url_for('seller_dashboard.booking_history'))

    # If form validation fails
    flash("Failed to submit feedback. Please check your inputs.", "danger")
    return redirect(url_for('seller_dashboard.booking_history'))


@seller_dashboard_bp.route('/edit-feedback/<int:feedback_id>', methods=['GET', 'POST'])
@login_required
def edit_feedback(feedback_id):
    feedback = InspectionFeedback.query.get_or_404(feedback_id)
    if feedback.user_id != current_user.id:
        abort(403)

    form = FeedbackForm(obj=feedback)
    if form.validate_on_submit():
        feedback.rating = form.rating.data
        feedback.comment = form.comment.data
        db.session.commit()
        flash("✏️ Feedback updated.", "success")
        return redirect(url_for('seller_dashboard.my_feedback'))

    return render_template('submit_feedback.html', form=form, editing=True)


@seller_dashboard_bp.route('/mark-booking-complete/<int:booking_id>', methods=['POST'])
@csrf.exempt  # ✅ Disable CSRF for this route
@login_required
def mark_booking_complete(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)

    if booking.buyer_id != current_user.id:
        abort(403)

    booking.inspection_marked_complete = True
    db.session.commit()
    flash("✅ Booking marked as complete.", "success")
    return redirect(request.referrer or url_for('seller_dashboard.inspection_history'))


from sqlalchemy import or_


from datetime import datetime, timedelta

@seller_dashboard_bp.route('/confirm-inspections')
@login_required
def confirm_inspections():
    print("[DEBUG] Logged-in user ID:", current_user.id)

    bookings = (
        db.session.query(BookingRequest)
        .join(Product, BookingRequest.product_id == Product.id)
        .filter(
            BookingRequest.inspection_reported_at.isnot(None),
            BookingRequest.inspection_marked_complete == True
        )
        .order_by(BookingRequest.created_at.desc())
        .all()
    )


def downgrade_expired_subscriptions():
    now = datetime.utcnow()
    expired = Subscription.query.filter(Subscription.end_date < now, Subscription.is_active == True).all()
    for sub in expired:
        sub.is_active = False
        db.session.commit()



@seller_dashboard_bp.route('/payment-success')
@login_required
def payment_success():
    from app.subscriptions.plans import subscription_plans
    plan = request.args.get('plan')
    payment_method = request.args.get('method', 'mock')
    plan_info = subscription_plans.get(plan)

    if not plan_info:
        flash("Invalid payment return.", "danger")
        return redirect(url_for('seller_dashboard.upgrade_plan'))

    new_sub = Subscription(
        user_id=current_user.id,
        plan=plan,
        price=plan_info['price'],

    )
    new_sub.activate(plan_info['duration_days'])

    db.session.add(new_sub)
    db.session.commit()

    flash(f"✅ Subscribed to {plan.upper()}!", "success")
    return redirect(url_for('seller_dashboard.my_dashboard'))


@seller_dashboard_bp.route('/admin/subscriptions')
@login_required
def admin_subscriptions():
    if current_user.role != 'admin':
        abort(403)
    all_subs = Subscription.query.order_by(Subscription.start_date.desc()).all()
    return render_template('admin/subscriptions.html', subscriptions=all_subs)

@seller_dashboard_bp.route('/mock-payment-initiate', methods=['POST'])
@login_required
def mock_payment_initiate():
    # Get the form data or JSON payload with amount, plan, etc.
    amount = request.form.get('amount')
    plan = request.form.get('plan')

    # Create a fake payment reference
    payment_reference = f"MOCKPAY-{uuid.uuid4().hex[:10].upper()}"

    # Normally, you would redirect user to Paystack or Flutterwave payment page.
    # Here, simulate by redirecting to a mock confirmation page.
    flash(f"Simulated payment initiation for {plan} plan: Ref {payment_reference}", "info")

    return redirect(url_for('seller_dashboard.mock_payment_verify', reference=payment_reference, plan=plan))

@seller_dashboard_bp.route('/mock-payment-verify')
@login_required
def mock_payment_verify():
    reference = request.args.get('reference')
    plan = request.args.get('plan')

    # Simulate verification success
    payment_success = True

    if payment_success:
        # Activate subscription
        from app.models import Subscription

        plan_info = {
            'free': {'price': 0},
            'starter': {'price': 5000},
            'pro': {'price': 15000},
            'business': {'price': 30000},
        }

        price = plan_info.get(plan, {}).get('price', 0)

        new_sub = Subscription(
            user_id=current_user.id,
            plan=plan,
            price=price,
            payment_method='mock',
            is_active=True
        )
        new_sub.activate(duration_days=30)
        db.session.add(new_sub)
        db.session.commit()

        flash(f"🎉 Mock payment successful! Subscribed to {plan.upper()}", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    else:
        flash("❌ Mock payment failed.", "danger")
        return redirect(url_for('seller_dashboard.upgrade_plan'))

@seller_dashboard_bp.route('/mock-webhook', methods=['POST'])
def mock_webhook():
    data = request.json
    # You can process incoming mock events here
    print("Received mock webhook data:", data)
    return jsonify({'status': 'success'}), 200


@seller_dashboard_bp.route('/flutterwave/initiate-payment', methods=['POST'])
@login_required
def flutterwave_initiate_payment():
    plan = request.form.get('plan')
    amount = request.form.get('amount')  # amount in NGN

    tx_ref = f"{current_user.id}_{uuid.uuid4().hex}"

    # Create a new subscription entry (pending)
    new_sub = Subscription(
        user_id=current_user.id,
        plan=plan,
        price=int(amount),
        payment_method='flutterwave',
        tx_ref=tx_ref,
        payment_status='pending',
        is_active=False
    )
    db.session.add(new_sub)
    db.session.commit()

    # Placeholder for actual Flutterwave redirect or simulation
    # Replace this with real payment redirect later
    flash(f"Payment initialized for {plan.upper()} plan (Ref: {tx_ref})", "info")
    return redirect(url_for('seller_dashboard.my_dashboard'))
  # or any confirmation route





# ✅ Add this route inside seller_dashboard_bp
@seller_dashboard_bp.route('/update-location', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()
    lat = data.get('latitude')
    lon = data.get('longitude')

    if lat and lon:
        current_user.latitude = lat
        current_user.longitude = lon
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'success'}), 200

    return jsonify({'status': 'failed', 'message': 'Missing coordinates'}), 400




@seller_dashboard_bp.route('/confirm_delivery/<int:escrow_id>', methods=['POST'])
@login_required
def confirm_delivery(escrow_id):
    escrow = Escrow.query.get_or_404(escrow_id)

    # Only buyer can confirm
    if escrow.buyer_id != current_user.id:
        abort(403)

    escrow.is_released = True
    escrow.released_at = datetime.utcnow()
    db.session.commit()

    # Optionally send notification to seller
    flash("Funds released to the seller.", "success")
    return redirect(url_for('buyer_dashboard'))

def generate_reference():
    return str(uuid.uuid4()).replace("-", "")[:12]  # Simple reference

import requests
import uuid

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY") # Replace with your secret key


@seller_dashboard_bp.route('/start_escrow/<int:product_id>', methods=['GET', 'POST'])
@login_required
def start_escrow(product_id):
    product = Product.query.get_or_404(product_id)
    form = EscrowPaymentForm()

    if form.validate_on_submit():
        amount = form.amount.data
        email = current_user.email
        callback_url = url_for('seller_dashboard.escrow_callback', _external=True)

        headers = {
            "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
            "Content-Type": "application/json"
        }
        data = {
            "email": email,
            "amount": int(amount * 100),  # Paystack expects amount in Kobo
            "callback_url": callback_url,
            "metadata": {
                "buyer_id": current_user.id,
                "product_id": product.id
            }
        }
        try:
            response = requests.post('https://api.paystack.co/transaction/initialize', json=data, headers=headers)
            result = response.json()
            if result.get('status') and result.get('data'):
                auth_url = result['data']['authorization_url']
                return redirect(auth_url)
            else:
                flash('Payment initialization failed. Please try again.', 'danger')
        except Exception as e:
            flash(f"An error occurred: {str(e)}", 'danger')

    return render_template('start_escrow.html', form=form, product=product)

@seller_dashboard_bp.route('/verify_escrow')
@login_required
def verify_escrow():
    reference = request.args.get('reference')
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }
    url = f"https://api.paystack.co/transaction/verify/{reference}"

    response = requests.get(url, headers=headers)
    res_data = response.json()

    if res_data.get("status") and res_data['data']['status'] == 'success':
        escrow = Escrow.query.filter_by(payment_reference=reference).first()
        if escrow:
            escrow.status = 'pending'  # Awaiting delivery or confirmation
            db.session.commit()
            flash('Escrow payment successful! Awaiting order completion.', 'success')
        else:
            flash('Escrow record not found.', 'danger')
    else:
        flash('Payment verification failed or not completed.', 'danger')

    return redirect(url_for('seller_dashboard.my_dashboard'))
@seller_dashboard_bp.route('/payment_callback')
@login_required
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        flash('No transaction reference found.', 'danger')
        return redirect(url_for('seller_dashboard.upgrade_plan'))

    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"
    }
    response = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    result = response.json()

    if result['status'] and result['data']['status'] == 'success':
        metadata = result['data'].get('metadata', {})
        plan_name = metadata.get('plan_name', 'Free')
        plan_duration_days = 30  # Or fetch dynamically from your Plan model

        expiry_date = datetime.utcnow() + timedelta(days=plan_duration_days)

        # Update or create a Subscription record
        subscription = Subscription.query.filter_by(user_id=current_user.id).first()

        if subscription:
            subscription.plan_name = plan_name
            subscription.expiry_date = expiry_date
            subscription.payment_reference = reference
        else:
            subscription = Subscription(
                user_id=current_user.id,
                plan_name=plan_name,
                expiry_date=expiry_date,
                payment_reference=reference,
                is_active=True
            )
            db.session.add(subscription)

        db.session.commit()
        flash('Your plan has been upgraded successfully!', 'success')
        return redirect(url_for('seller_dashboard.dashboard_home'))
    else:
        flash('Payment verification failed. Please contact support.', 'danger')
        return redirect(url_for('seller_dashboard.upgrade_plan'))

@seller_dashboard_bp.route('/verify_escrow_payment')
def verify_escrow_payment():
    reference = request.args.get('reference')
    paystack_secret_key = current_app.config['PAYSTACK_SECRET_KEY']

    headers = {
        'Authorization': f'Bearer {paystack_secret_key}',
    }

    import requests
    response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
    result = response.json()

    if result.get('status') and result['data']['status'] == 'success':
        escrow = Escrow.query.filter_by(payment_reference=reference).first()
        if escrow:
            escrow.status = 'paid'
            db.session.commit()
            flash('Payment successful and recorded!', 'success')
        return redirect(url_for('seller_dashboard.dashboard'))

    flash('Payment not successful or verification failed.', 'danger')
    return redirect(url_for('seller_dashboard.dashboard'))

@seller_dashboard_bp.route('/subscription/upgrade')
@login_required
def show_plans():
    plans = SubscriptionPlan.query.all()
    # Replace any 'inf' string with a sentinel
    for plan in plans:
        if str(plan.upload_limit).lower() in ['inf', 'infinity']:
            plan.upload_limit = 'unlimited'
    return render_template('upgrade_plan.html', plans=plans)





@seller_dashboard_bp.route('/initiate_payment', methods=['POST'])
@login_required
def initiate_payment():
    try:
        email = request.form['email']
        amount = int(request.form['amount'])  # This must be an integer
        plan_name = request.form['plan_name']
    except KeyError as e:
        return f"Missing form field: {e}", 400

    return render_template("payment_page.html", email=email, amount=amount,
                           plan_name=plan_name, paystack_public_key=current_app.config['PAYSTACK_PUBLIC_KEY'])


@seller_dashboard_bp.route('/verify_payment', methods=['GET'])
@login_required
def verify_payment():
    reference = request.args.get('reference')
    plan = request.args.get('plan_name')  # e.g., 'Starter'

    # ✅ Step 1: Verify the payment using Paystack
    is_successful = verify_paystack_payment(reference)  # Replace with your actual verification logic

    if is_successful:
        # ✅ Step 2: Plan limits and durations (all paid plans = 30 days)
        plan_configs = {
            'Free': {'limit': 2, 'duration_days': 0},
            'Starter': {'limit': 10, 'duration_days': 30},
            'Business': {'limit': 50, 'duration_days': 30},
            'Premium': {'limit': 200, 'duration_days': 30},
        }

        config = plan_configs.get(plan, plan_configs['Free'])

        # ✅ Step 3: Update user details
        current_user.plan_name = plan
        current_user.upload_limit = config['limit']

        # ✅ Set subscription start and end dates for paid plans
        if plan != 'Free':
            current_user.subscription_start = datetime.utcnow()
            current_user.subscription_end = datetime.utcnow() + timedelta(days=config['duration_days'])
            current_user.grace_end = current_user.subscription_end + timedelta(days=3)
        else:
            current_user.subscription_start = None
            current_user.subscription_end = None
            current_user.grace_end = None

        db.session.commit()

        flash(f"🎉 {plan} plan activated successfully!", "success")
    else:
        flash("❌ Payment verification failed. Please try again.", "danger")

    return redirect(url_for('seller_dashboard.my_dashboard'))



@seller_dashboard_bp.route('/initiate_payment', methods=['POST'])
@login_required
def process_upgrade():
    selected_plan = request.form.get('plan')

    plans = {
        "Free": {"price": 0, "upload_limit": 2},
        "Starter": {"price": 100, "upload_limit": 5},
        "Pro": {"price": 300, "upload_limit": 10},
        "Business": {"price": 500, "upload_limit": float('inf')},
    }

    plan = plans.get(selected_plan)

    if not plan:
        flash("❌ Invalid plan selected.", "danger")
        return redirect(url_for('seller_dashboard.upgrade_plan'))

    # Save data in session for use in payment
    session['selected_plan'] = selected_plan
    session['plan_price'] = plan['price']
    session['upload_limit'] = plan['upload_limit']

    return redirect(url_for('seller_dashboard.initiate_payment', plan_name=selected_plan))


@seller_dashboard_bp.route('/upgrade-plan', methods=['GET', 'POST'])
@login_required
def upgrade_plan():
    plans = SubscriptionPlan.query.all()  # Get all available plans from DB

    if request.method == 'POST':
        selected_plan_name = request.form.get('plan')
        selected_plan = SubscriptionPlan.query.filter_by(name=selected_plan_name).first()

        if not selected_plan:
            flash("❌ Invalid plan selected.", "danger")
            return redirect(url_for('seller_dashboard.upgrade_plan'))

        # Optionally save selected plan temporarily in session or user profile before payment

        # Redirect to payment page to process subscription upgrade
        return redirect(url_for('subscription.create_payment', plan_name=selected_plan.name))

    return render_template('upgrade_plan.html', plans=plans, user=current_user)


# seller_dashboard/routes.py


def create_recipient_code(account_number, bank_code, account_name):
    """Calls Paystack to create a transfer recipient."""
    url = "https://api.paystack.co/transferrecipient"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "type": "nuban",
        "name": account_name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN"
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result.get("status"):
        return result["data"]["recipient_code"]
    else:
        raise ValueError(result.get("message", "Unable to create recipient."))

@seller_dashboard_bp.route("/setup-payout", methods=["GET", "POST"])
@login_required
def setup_payout():
    form = PayoutForm()
    headers = {"Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"}

    # Fetch banks
    banks = []
    bank_response = requests.get("https://api.paystack.co/bank", headers=headers)
    if bank_response.status_code == 200:
        banks = bank_response.json().get("data", [])
        form.bank_name.choices = [(bank["code"], bank["name"]) for bank in banks]
    else:
        flash("Could not load banks", "danger")

    if form.validate_on_submit():
        bank_code = form.bank_name.data
        account_number = form.account_number.data
        account_name = form.account_name.data

        # Create recipient on Paystack
        payload = {
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN"
        }
        response = requests.post("https://api.paystack.co/transferrecipient", json=payload, headers=headers)
        result = response.json()

        if result.get("status"):
            recipient_code = result["data"]["recipient_code"]

            # Always create a new bank record
            bank_details = BankDetails(
                user_id=current_user.id,
                bank_name=dict(form.bank_name.choices).get(bank_code),
                bank_code=bank_code,
                account_number=account_number,
                account_name=account_name,
                recipient_code=recipient_code
            )
            db.session.add(bank_details)
            db.session.commit()

            flash("Bank account added successfully", "success")
            return redirect(url_for("seller_dashboard.view_bank_details"))
        else:
            flash("Paystack Error: " + result.get("message", "Could not create recipient"), "danger")

    # Get all accounts for display
    bank_accounts = BankDetails.query.filter_by(user_id=current_user.id).all()
    return render_template("setup_payout.html", form=form, banks=banks, bank_accounts=bank_accounts)

# ✅ AJAX route to resolve account name
@seller_dashboard_bp.route("/resolve-account", methods=["POST"])
@login_required
def resolve_account():
    data = request.get_json()
    account_number = data.get("account_number")
    bank_code = data.get("bank_code")

    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"
    }

    url = f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200 and response.json().get("status"):
        return jsonify({"success": True, "account_name": response.json()["data"]["account_name"]})
    return jsonify({"success": False, "message": "Account resolution failed"})

@seller_dashboard_bp.route('/bank-details-update', methods=['GET', 'POST'])
@login_required
def update_bank_details():
    form = BankDetailsForm()
    if form.validate_on_submit():
        account_number = form.account_number.data
        bank_code = form.bank_name.data  # Make sure form field name matches (bank_name or bank_code)

        # Call Paystack to resolve account name
        resolved = resolve_account_name(account_number, bank_code)
        if not resolved.get("status"):
            flash("Bank verification failed.", "danger")
            return render_template("seller_dashboard/bank_details.html", form=form)

        # Find or create BankDetails record for the user
        details = BankDetails.query.filter_by(user_id=current_user.id).first()
        if not details:
            details = BankDetails(user_id=current_user.id)

        details.account_number = account_number
        details.bank_code = bank_code
        details.bank_name = resolved["data"]["bank_name"]
        details.account_name = resolved["data"]["account_name"]

        # Create recipient code with Paystack
        recipient_code = create_recipient_code(account_number, bank_code)
        details.recipient_code = recipient_code

        db.session.add(details)
        db.session.commit()

        flash("Bank details updated successfully", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    return render_template("seller_dashboard/bank_details.html", form=form)


# app/seller_dashboard/routes.py or similar
@seller_dashboard_bp.route("/view-bank-details")
@login_required
def view_bank_details():
    bank_details = BankDetails.query.filter_by(user_id=current_user.id).all()
    return render_template("bank_details.html", bank_details=bank_details)

@seller_dashboard_bp.route("/delete-bank-account/<int:account_id>", methods=["POST"])
@login_required
def delete_bank_account(account_id):
    bank = BankDetails.query.filter_by(id=account_id, user_id=current_user.id).first()

    if not bank:
        flash("Bank account not found.", "danger")
        return redirect(url_for("seller_dashboard.view_bank_details"))

    db.session.delete(bank)
    db.session.commit()
    flash("Bank account deleted successfully.", "success")
    return redirect(url_for("seller_dashboard.view_bank_details"))




@seller_dashboard_bp.route("/api/get-banks", methods=["GET"])
def get_banks():
    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"
    }
    response = requests.get("https://api.paystack.co/bank", headers=headers)

    if response.status_code == 200:
        banks = response.json().get("data", [])
        return jsonify(banks)
    return jsonify([]), 500


@seller_dashboard_bp.route("/create-recipient", methods=["POST"])
@login_required
def create_recipient():
    form = BankDetailsForm()

    if form.validate_on_submit():
        bank_code = form.bank_name.data
        account_number = form.account_number.data
        account_name = form.account_name.data

        payload = {
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN"
        }

        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post("https://api.paystack.co/transferrecipient", json=payload, headers=headers)
        data = response.json()

        if data.get("status"):
            recipient_code = data["data"]["recipient_code"]

            # ✅ Save to database
            existing = BankDetails.query.filter_by(user_id=current_user.id).first()
            if not existing:
                new_details = BankDetails(
                    user_id=current_user.id,
                    account_name=account_name,
                    account_number=account_number,
                    bank_code=bank_code,
                    recipient_code=recipient_code
                )
                db.session.add(new_details)
            else:
                existing.account_name = account_name
                existing.account_number = account_number
                existing.bank_code = bank_code
                existing.recipient_code = recipient_code

            db.session.commit()

            flash("Bank account saved successfully!", "success")
            return redirect(url_for("seller_dashboard.setup_payout"))
        else:
            flash("Error creating recipient: " + data.get("message", "Unknown error"), "danger")
            return redirect(url_for("seller_dashboard.setup_payout"))

    flash("Form validation failed.", "danger")
    return redirect(url_for("seller_dashboard.setup_payout"))

from flask import flash, redirect, url_for
import requests
from datetime import datetime
from app.models import EscrowPayment, User
from flask_login import login_required, current_user
from app import db


@seller_dashboard_bp.route("/confirm-order/<int:escrow_id>", methods=["POST"])
@login_required
def confirm_order(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    # ✅ Only buyer can confirm the order
    if escrow.buyer_id != current_user.id:
        abort(403)

    if not escrow.is_paid or escrow.is_disbursed:
        flash("Invalid order status", "warning")
        return redirect(url_for("dashboard.escrow_transactions"))

    seller = User.query.get(escrow.seller_id)
    if not seller.recipient_code:
        flash("Seller payout setup is incomplete", "danger")
        return redirect(url_for("dashboard.escrow_transactions"))

    # ✅ Paystack setup
    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }

    total_amount_kobo = int(escrow.base_amount * 100)
    admin_fee_kobo = int((escrow.admin_fee or 0) * 100)
    seller_amount_kobo = total_amount_kobo - admin_fee_kobo

    # 🔁 Payout to Seller
    seller_payload = {
        "source": "balance",
        "amount": seller_amount_kobo,
        "recipient": seller.recipient_code,
        "reason": f"Payout to Seller for Escrow #{escrow.id}"
    }

    seller_res = requests.post("https://api.paystack.co/transfer", json=seller_payload, headers=headers)
    seller_result = seller_res.json()

    if seller_res.status_code == 200 and seller_result.get("status"):
        # 🔁 Payout to Admin (Admin recipient code from config or DB)
        admin_recipient = current_app.config.get("ADMIN_RECIPIENT_CODE")  # e.g., from config
        if admin_fee_kobo > 0 and admin_recipient:
            admin_payload = {
                "source": "balance",
                "amount": admin_fee_kobo,
                "recipient": admin_recipient,
                "reason": f"Admin fee for Escrow #{escrow.id}"
            }
            admin_res = requests.post("https://api.paystack.co/transfer", json=admin_payload, headers=headers)
            admin_result = admin_res.json()

            # Save admin revenue even if it fails (log or alert in future)
            if admin_res.status_code == 200 and admin_result.get("status"):
                admin_revenue = AdminRevenue(
                    amount=escrow.admin_fee,
                    source="escrow",
                    reference=admin_result["data"]["reference"]
                )
                db.session.add(admin_revenue)

        # ✅ Record seller payout
        payout = PayoutTransaction(
            user_id=seller.id,
            amount=seller_amount_kobo,
            reference=seller_result["data"]["reference"],
            status="success"
        )
        db.session.add(payout)

        # ✅ Update escrow status
        escrow.status = "completed"
        escrow.is_disbursed = True
        db.session.commit()

        flash("Order confirmed. Payments disbursed.", "success")
    else:
        flash("Payout failed: " + seller_result.get("message", "Unknown error"), "danger")

    return redirect(url_for("dashboard.escrow_transactions"))

@seller_dashboard_bp.route("/send-payout/<int:user_id>", methods=["POST"])
@login_required
def send_payout(user_id):
    user = User.query.get_or_404(user_id)

    if not user.recipient_code:
        flash("Recipient not set up", "danger")
        return redirect(url_for("seller_dashboard.view_bank_details"))

    amount_naira = 5000  # Example: 5,000 NGN
    amount_kobo = amount_naira * 100  # Paystack expects amount in kobo

    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }

    payload = {
        "source": "balance",
        "amount": amount_kobo,
        "recipient": user.recipient_code,
        "reason": f"Payout to {user.first_name} ({user.email})"
    }

    response = requests.post("https://api.paystack.co/transfer", json=payload, headers=headers)
    result = response.json()

    if response.status_code == 200 and result.get("status"):
        flash("Payout sent successfully!", "success")
    else:
        flash("Payout failed: " + result.get("message", "Unknown error"), "danger")

    return redirect(url_for("seller_dashboard.view_bank_details"))


@seller_dashboard_bp.route("/escrow-summary")
@login_required
def escrow_summary():
    if current_user.role != "seller":
        return render_template("seller/escrow_summary.html")  # No totals

    pending = db.session.query(func.sum(Escrow.amount)).filter_by(
        seller_id=current_user.id,
        status="PENDING"
    ).scalar() or 0.0

    released = db.session.query(func.sum(Escrow.amount)).filter_by(
        seller_id=current_user.id,
        status="RELEASED"
    ).scalar() or 0.0

    withdrawn = db.session.query(func.sum(Escrow.amount)).filter_by(
        seller_id=current_user.id,
        status="WITHDRAWN"
    ).scalar() or 0.0

    return render_template("seller/escrow_summary.html", pending_amount=pending, released_amount=released, withdrawn_amount=withdrawn)


@seller_dashboard_bp.route("/my-escrow-summa")
@login_required
def user_escrow():
    role = current_user.role.lower()

    if role == 'buyer':
        escrows = Escrow.query.filter_by(buyer_id=current_user.id).order_by(Escrow.created_at.desc()).all()
    elif role == 'seller':
        escrows = Escrow.query.filter_by(seller_id=current_user.id).order_by(Escrow.created_at.desc()).all()
    else:
        escrows = []

    return render_template("dashboard/escrow.html", escrows=escrows, role=role)
from app.utils.paystack import transfer_funds_to_seller

@seller_dashboard_bp.route("/wallet-history")
@login_required
def wallet_history():
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    transactions = wallet.transactions if wallet else []
    return render_template("wallet/history.html", transactions=transactions)


@seller_dashboard_bp.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    # Get or create wallet for current user
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    if not wallet:
        wallet = Wallet(user_id=current_user.id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()

    # Withdrawal form
    form = WithdrawalForm()

    # Get saved bank accounts
    bank_accounts = BankDetails.query.filter_by(user_id=current_user.id).all()
    form.bank_account.choices = [(b.id, f"{b.bank_name} - {b.account_number}") for b in bank_accounts]

    if request.method == "POST" and form.validate_on_submit():
        selected_bank = BankDetails.query.get(form.bank_account.data)
        amount = form.amount.data

        if not selected_bank:
            flash("Selected bank not found.", "danger")
            return redirect(url_for("seller_dashboard.withdraw"))

        if amount > wallet.balance:
            flash("Insufficient balance.", "danger")
            return redirect(url_for("seller_dashboard.withdraw"))

        # Use your existing payout utility
        transfer_result = initiate_paystack_transfer(
            bank_code=selected_bank.bank_code,
            account_number=selected_bank.account_number,
            amount=int(amount * 100),  # Paystack expects kobo
            name=selected_bank.account_name
        )

        if transfer_result.get("status"):
            wallet.balance -= amount
            db.session.commit()
            flash(f"Withdrawal of ₦{amount:,.2f} initiated successfully.", "success")
            return redirect(url_for("seller_dashboard.withdraw"))
        else:
            flash("Withdrawal failed: " + transfer_result.get("message", "Unknown error"), "danger")

    return render_template(
        "wallet/withdraw.html",
        form=form,
        wallet=wallet,
        bank_accounts=bank_accounts
    )



@seller_dashboard_bp.route("/products")
@login_required
def my_products():
    products = Product.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(Product.created_at.desc()).all()
    return render_template("list.html", products=products,now=datetime.utcnow())



@seller_dashboard_bp.route("/orders")
@login_required
def my_orders():
    buyer_orders = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).all()
    seller_orders = Order.query.filter_by(seller_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("orders_list.html", buyer_orders=buyer_orders, seller_orders=seller_orders)


@seller_dashboard_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)

    # derive normalized status name from Enum
    status_name = order.status.name.lower()  # 'pending', 'accepted', 'shipped', ...

    actions = []
    if status_name == "pending":
        if current_user.id == order.seller_id:
            actions = ["accepted", "canceled"]    # seller can accept or cancel
        elif current_user.id == order.buyer_id:
            actions = ["canceled"]                 # buyer can cancel
    elif status_name == "accepted":
        if current_user.id == order.seller_id:
            actions = ["shipped", "canceled"]      # seller can ship or cancel
        elif current_user.id == order.buyer_id:
            actions = ["canceled"]                 # (optional) allow buyer cancel
    elif status_name == "shipped":
        if current_user.id == order.buyer_id:
            actions = ["completed"]                # buyer confirms completion
    product = Product.query.get(order.product_id)
    escrow = EscrowPayment.query.filter_by(product_id=product.id).first()
    return render_template(
        "order_detail.html",
        order=order,
        actions=actions,
        product=product,
        escrow=escrow
    )



from datetime import datetime
from app.models import StatusEnum

@seller_dashboard_bp.route("/orders/<int:order_id>/update-status", methods=["GET", "POST"])
@login_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)

    # Restrict access to buyer or seller
    if current_user.id not in [order.buyer_id, order.seller_id]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order_id))

    # Get new status from form, clean it
    new_status = (request.form.get("status") or "").strip().lower()

    if not new_status:
        flash("No status provided.", "warning")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order_id))

    # Current status in lowercase
    current_status = order.status.value.lower()

    # Define allowed transitions
    valid_transitions = {
        "pending":  ["accepted", "canceled"],
        "accepted": ["shipped", "canceled"],
        "shipped":  ["completed"],
        # You can optionally add more (e.g. rollback paths)
    }

    # Check if transition is valid
    if new_status not in valid_transitions.get(current_status, []):
        flash(f"Invalid status transition from '{current_status}' to '{new_status}'.", "warning")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order_id))

    # Match new_status to StatusEnum by .value
    matched_status = next((s for s in StatusEnum if s.value.lower() == new_status), None)

    if not matched_status:
        flash("Invalid status value submitted.", "danger")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order_id))

    # Update and commit
    order.status = matched_status
    order.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f"Order status updated to '{order.status.value}'.", "success")
    return redirect(url_for("seller_dashboard.order_detail", order_id=order_id))

from app.models import StatusEnum


@seller_dashboard_bp.route("/update-order/<int:order_id>", methods=["POST", "GET"])
@login_required
def update_order(order_id):
    order = Order.query.get_or_404(order_id)

    new_status_str = request.form.get("status")  # e.g. 'Accepted', 'Canceled'

    try:
        # Convert form string to enum safely
        order.status = StatusEnum[new_status_str.upper()]
        order.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Order status updated to {new_status_str}.", "success")
    except KeyError:
        flash("Invalid status selected.", "danger")

    return redirect(url_for("seller_dashboard.order_details", order_id=order.id))

# Pending Orders
@seller_dashboard_bp.route('/pending-orders')
@login_required
def pending_orders():
    orders = Order.query.filter_by(status='pending').all()
    return render_template('pending_orders.html', orders=orders)

# Completed Orders
@seller_dashboard_bp.route('/completed-orders')
@login_required
def completed_orders():
    orders = Order.query.filter_by(status='completed').all()
    return render_template('completed_orders.html', orders=orders)

@seller_dashboard_bp.route('/wishlist')
@login_required
def wishlist():
    items = Wishlist.query.filter_by(user_id=current_user.id).join(Product).all()
    return render_template('wishlist.html', items=items)

@seller_dashboard_bp.route('/wishlist/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_wishlist(product_id):
    existing = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if not existing:
        wishlist_item = Wishlist(user_id=current_user.id, product_id=product_id)
        db.session.add(wishlist_item)
        db.session.commit()
        flash('Product added to your wishlist.', 'success')
    else:
        flash('Product already in wishlist.', 'info')
    return redirect(request.referrer or url_for('seller_dashboard.view_product', product_id=product_id))

@seller_dashboard_bp.route('/wishlist/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_wishlist(item_id):
    item = Wishlist.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash('Removed from wishlist.', 'success')
    return redirect(url_for('seller_dashboard.wishlist'))

from flask_login import current_user
from sqlalchemy import and_

@seller_dashboard_bp.route('/bookings')
@login_required
def booking_dashboard():
    # Upcoming bookings: buyer's bookings not rejected and inspection not reported yet
    upcoming_bookings = BookingRequest.query.filter(
        BookingRequest.buyer_id == current_user.id,
        BookingRequest.status != 'rejected',
        BookingRequest.inspection_reported_at.is_(None)
    ).order_by(BookingRequest.booking_time.desc()).all()

    # Completed bookings: buyer's bookings with inspection reported and buyer marked complete
    completed_bookings = BookingRequest.query.filter(
        BookingRequest.buyer_id == current_user.id,
        BookingRequest.inspection_reported_at.isnot(None),
        BookingRequest.inspection_marked_complete == True
    ).order_by(BookingRequest.booking_time.desc()).all()

    return render_template(
        'booking_dashboard.html',
        upcoming_bookings=upcoming_bookings,
        completed_bookings=completed_bookings
    )


@seller_dashboard_bp.route('/edit-product-review/<int:review_id>', methods=['GET', 'POST'])
@login_required
def edit_product_review(review_id):
    review = ProductReview.query.get_or_404(review_id)

    if review.reviewer_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('seller_dashboard.product_detail', product_id=review.product_id))

    if request.method == 'POST':
        review.rating = request.form.get('rating')
        review.comment = request.form.get('comment')
        db.session.commit()
        flash("Review updated.", "success")
        return redirect(url_for('seller_dashboard.product_detail', product_id=review.product_id))

    return render_template('edit_product_review.html', review=review)

@seller_dashboard_bp.route('/delete-product-review/<int:review_id>', methods=['POST', 'GET'])
@login_required
def delete_product_review(review_id):
    review = ProductReview.query.get_or_404(review_id)

    if review.reviewer_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('seller_dashboard.product_detail', product_id=review.product_id))

    db.session.delete(review)
    db.session.commit()
    flash("Review deleted.", "success")
    return redirect(url_for('seller_dashboard.product_detail', product_id=review.product_id))

from sqlalchemy import func
from math import radians, cos, sin, asin, sqrt
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@seller_dashboard_bp.route("/agents-in-state/<int:product_id>")
def agents_in_state(product_id):
    product = Product.query.get_or_404(product_id)

    if product.latitude is None or product.longitude is None:
        flash("Product location not set.", "warning")
        return redirect(url_for("seller_dashboard.product_detail", product_id=product.id))

    agents = User.query.filter_by(role="agent", state=product.state).filter(
        User.latitude.isnot(None),
        User.longitude.isnot(None)
    ).all()

    agent_data = []
    for agent in agents:
        distance = haversine(product.latitude, product.longitude, agent.latitude, agent.longitude)
        agent_data.append({
            "agent": agent,
            "distance": round(distance, 2),
            "is_online": agent.is_online or False
        })

    # Sort: online first, then by distance
    sorted_agents = sorted(agent_data, key=lambda x: (not x["is_online"], x["distance"]))

    return render_template("search_agents.html", product=product, agents=sorted_agents)

@seller_dashboard_bp.route('/wallet')
@login_required
def wallet_page():
    wallet = get_or_create_wallet(current_user.id)
    transactions = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(WalletTransaction.created_at.desc()).all()
    return render_template('wallet.html', wallet=wallet, transactions=transactions)


@seller_dashboard_bp.route("/orders/<int:order_id>/<action>", methods=["POST"])
@login_required
def handle_order_action(order_id, action):
    order = Order.query.get_or_404(order_id)

    # Ensure only relevant users can act
    if current_user.id not in [order.seller_id, order.buyer_id]:
        flash("You are not authorized to perform this action.", "danger")
        return redirect(url_for("seller_dashboard.my_orders"))

    # Normalize action
    action = action.lower()

    # Seller actions
    if current_user.id == order.seller_id:
        if action == "accepted":
            order.status = StatusEnum.accepted
            flash("Order accepted.", "success")
        elif action == "shipped":
            order.status = StatusEnum.shipped
            flash("Order marked as shipped.", "success")
        elif action == "canceled":
            order.status = StatusEnum.canceled
            flash("Order canceled.", "warning")
    # Buyer actions
    elif current_user.id == order.buyer_id:
        if action == "completed":
            order.status = StatusEnum.completed
            flash("Order marked as completed.", "success")
        elif action == "canceled":
            order.status = StatusEnum.canceled
            flash("Order canceled.", "warning")
        elif action == "paid":
            order.status = StatusEnum.paid
            flash("Order marked as paid.", "success")

    db.session.commit()
    return redirect(url_for("seller_dashboard.order_detail", order_id=order.id))




@seller_dashboard_bp.route('/wallet')
@login_required
def wallet():
    # Fetch user info and transfers
    user = current_user
    sent_transfers = user.sent_transfers
    received_transfers = user.received_transfers

    # Optional: fetch all recipients grouped by type
    recipients = User.query.filter(User.id != current_user.id).all()

    return render_template(
        'dashboard.html',
        user=user,
        balance=user.wallet_balance,
        products=user.products,  # if needed
        recipients=recipients,
        sent_transfers=sent_transfers,
        received_transfers=received_transfers
    )


# in seller_dashboard routes
# in seller_dashboard routes
@seller_dashboard_bp.route("/get_recipients/<recipient_type>")
@login_required
def get_recipients(recipient_type):
    recipients = []

    if recipient_type == "direct_seller":
        recipients = User.query.filter_by(role="seller").all()
    elif recipient_type == "direct_agent":
        recipients = User.query.filter_by(role="agent").all()
    elif recipient_type == "direct_logistics":
        recipients = User.query.filter_by(role="logistics").all()
    elif recipient_type == "direct_vet":
        recipients = User.query.filter_by(role="vet").all()

    # Escrow types → still fetch ALL agents/logistics, not just is_escrow
    elif recipient_type == "escrow_agent":
        recipients = User.query.filter_by(role="agent").all()
    elif recipient_type == "escrow_logistics":
        recipients = User.query.filter_by(role="logistics").all()

    return jsonify([
        {"id": u.id, "name": f"{u.first_name} {u.last_name} ({u.role.title()})"}
        for u in recipients
    ])



from decimal import Decimal, ROUND_HALF_UP

@seller_dashboard_bp.route('/transfer-funds', methods=['POST'])
@login_required
def transfer_funds():
    sender = current_user
    amount = Decimal(request.form.get('amount', '0.00')).quantize(Decimal("0.01"))
    recipient_type = request.form.get('recipient_type')
    recipient_id = int(request.form.get('recipient_id'))

    if amount <= 0:
        flash("Enter a valid amount.", "warning")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    # ---------- Escrow Transfer ----------
    if recipient_type in ["escrow_agent", "escrow_logistics"]:
        escrow_type = "agent" if recipient_type == "escrow_agent" else "logistics"

        # Calculate admin fee (3%) and total
        admin_fee = (amount * Decimal("0.03")).quantize(Decimal("0.01"))
        total_amount = amount + admin_fee

        # Deduct total from buyer wallet
        buyer_wallet = get_or_create_wallet(sender.id)
        if buyer_wallet.balance < total_amount:
            flash("Insufficient funds!", "danger")
            return redirect(url_for('seller_dashboard.my_dashboard'))

        buyer_wallet.balance -= total_amount
        db.session.add(WalletTransaction(
            wallet_id=buyer_wallet.id,
            user_id=sender.id,
            amount=-total_amount,
            transaction_type="escrow_hold",
            description=f"Escrow payment holding for {escrow_type} User {recipient_id}",
            reference=str(uuid.uuid4())
        ))

        # Create new escrow record
        escrow = EscrowPayment(
            buyer_id=sender.id,
            provider_id=recipient_id,
            product_id=None,
            amount=amount,             # Portion for agent/seller
            total_amount=total_amount, # Includes admin fee
            base_amount=amount,        # Only what agent/seller will receive
            escrow_fee=admin_fee,
            status="paid",
            is_paid=True,
            type=escrow_type,
            reference=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            partial_release_amount=Decimal("0.00")  # Not released yet
        )
        db.session.add(escrow)
        db.session.commit()

        flash(f"Escrow payment of ₦{amount:.2f} created for {escrow_type}. Admin fee: ₦{admin_fee:.2f}.", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    # ---------- Direct Wallet Transfer ----------
    else:
        recipient_wallet = get_or_create_wallet(recipient_id)
        sender_wallet = get_or_create_wallet(sender.id)

        if sender_wallet.balance < amount:
            flash("Insufficient funds!", "danger")
            return redirect(url_for('seller_dashboard.my_dashboard'))

        sender_wallet.balance -= amount
        recipient_wallet.balance += amount

        db.session.add(WalletTransaction(
            wallet_id=sender_wallet.id,
            user_id=sender.id,
            amount=-amount,
            transaction_type="debit",
            description=f"Direct payment to {recipient_type} User {recipient_id}",
            reference=str(uuid.uuid4())
        ))
        db.session.add(WalletTransaction(
            wallet_id=recipient_wallet.id,
            user_id=recipient_id,
            amount=amount,
            transaction_type="credit",
            description=f"Received direct payment from User {sender.id}",
            reference=str(uuid.uuid4())
        ))
        db.session.commit()

        flash(f"Direct payment of ₦{amount:.2f} successful!", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

@seller_dashboard_bp.route('/my-escrows')
@login_required
def my_escrows():
    # Fetch all escrow payments for the current user (buyer or seller)
    escrows = EscrowPayment.query.filter_by(buyer_id=current_user.id).all()

    # Collect products for each escrow
    # If your EscrowPayment model has a relationship to Product, you can access it directly
    # e.g., escrow.product.id
    return render_template(
        "escrow/view_escrow.html",
        escrows=escrows
    )




@seller_dashboard_bp.route("/admin/release_escrow/<int:escrow_id>", methods=["POST"])
@login_required
def admin_release_escrow(escrow_id):
    # Check if current_user is admin
    if current_user.role != "admin":
        abort(403)

    escrow = EscrowPayment.query.get_or_404(escrow_id)
    release_escrow(escrow)
    return jsonify({"status": "success", "message": "Escrow released"})


@seller_dashboard_bp.route("/dashboard/escrow/mark_complete/<int:escrow_id>", methods=["POST"])
@login_required
def mark_complete(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)
    role = request.json.get("role")

    if role == "buyer" and current_user.id == escrow.payer_id:
        escrow.completed_by_buyer = True
    elif role in ["agent", "logistics"] and current_user.id == escrow.provider_id:
        escrow.completed_by_provider = True
    else:
        abort(403)

    escrow.check_ready()

    # Notify parties
    socketio.emit(
        "escrow_update",
        {
            "escrow_id": escrow.id,
            "released_amount": escrow.partial_release_amount,
            "pending_amount": escrow.amount - escrow.partial_release_amount,
            "status": escrow.status
        },
        to=f"user_{escrow.payer_id}"
    )
    socketio.emit(
        "escrow_update",
        {
            "escrow_id": escrow.id,
            "released_amount": escrow.partial_release_amount,
            "pending_amount": escrow.amount - escrow.partial_release_amount,
            "status": escrow.status
        },
        to=f"user_{escrow.provider_id}"
    )

    return jsonify({"status":"success","escrow_status":escrow.status})


# -----------------
# Utility: Get or Create Wallet
# -----------------
def get_or_create_wallet(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()
    return wallet

# -----------------
# Direct Payment (no escrow)
# -----------------
@seller_dashboard_bp.route("/pay-direct/<int:provider_id>", methods=["POST"])
@login_required
def pay_direct(provider_id):
    buyer = current_user
    amount = float(request.form.get("amount"))

    buyer_wallet = get_or_create_wallet(buyer.id)
    provider_wallet = get_or_create_wallet(provider_id)

    if buyer_wallet.balance < amount:
        flash("Insufficient funds in wallet.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # Deduct from buyer
    buyer_wallet.balance -= amount

    txn1 = WalletTransaction(
        wallet_id=buyer_wallet.id,
        user_id=buyer.id,
        amount=-amount,
        transaction_type="debit",
        description=f"Direct payment to provider {provider_id}",
        reference=str(uuid.uuid4()),
    )
    db.session.add(txn1)

    # Credit provider
    provider_wallet.balance += amount

    txn2 = WalletTransaction(
        wallet_id=provider_wallet.id,
        user_id=provider_id,
        amount=amount,
        transaction_type="credit",
        description=f"Direct payment received from buyer {buyer.id}",
        reference=str(uuid.uuid4()),
    )
    db.session.add(txn2)

    db.session.commit()
    flash("Direct payment completed successfully.", "success")
    return redirect(url_for("seller_dashboard.my_dashboard"))

# -----------------
# Escrow Payment (hold funds)
# -----------------
@seller_dashboard_bp.route("/pay-escrow/<int:provider_id>", methods=["POST"])
@login_required
def pay_escrow(provider_id):
    buyer = current_user
    amount = float(request.form.get("amount"))

    buyer_wallet = get_or_create_wallet(buyer.id)

    if buyer_wallet.balance < amount:
        flash("Insufficient funds in wallet.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # Deduct from buyer wallet & hold in escrow
    buyer_wallet.balance -= amount

    escrow = EscrowPayment(
        buyer_id=buyer.id,
        provider_id=provider_id,
        amount=amount,
        status="pending"
    )
    db.session.add(escrow)
    db.session.flush()  # so escrow.id is available

    txn = WalletTransaction(
        wallet_id=buyer_wallet.id,
        user_id=buyer.id,
        related_escrow_id=escrow.id,
        amount=-amount,
        transaction_type="escrow_hold",
        description=f"Escrow hold for provider {provider_id}",
        reference=str(uuid.uuid4()),
    )
    db.session.add(txn)

    db.session.commit()
    flash("Funds placed in escrow successfully.", "success")
    return redirect(url_for("seller_dashboard.my_dashboard"))

# -----------------
# Release Escrow (with 3% fee deduction)
# -----------------
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

from decimal import Decimal, ROUND_HALF_UP
from flask import request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import uuid

from decimal import Decimal
from flask import request, redirect, url_for, flash

from decimal import Decimal, ROUND_HALF_UP
from flask import flash, redirect, url_for, request
from flask_login import login_required, current_user

# seller_dashboard.py (inside your blueprint)

from decimal import Decimal, ROUND_HALF_UP
from flask import request, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import EscrowPayment, Wallet, WalletTransaction

from decimal import Decimal, ROUND_HALF_UP

@seller_dashboard_bp.route('/release-escrow/<int:escrow_id>', methods=['POST'])
@login_required
def release_escrow(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    try:
        if not escrow.is_paid:
            flash("Escrow payment not verified.", "warning")
            return redirect(url_for('seller_dashboard.my_dashboard'))

        if escrow.is_released:
            flash("Escrow already released.", "warning")
            return redirect(url_for('seller_dashboard.my_dashboard'))

        # Convert amounts to Decimal
        agent_amount = Decimal(escrow.base_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        admin_amount = Decimal(escrow.escrow_fee or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Credit agent wallet
        agent_wallet = Wallet.query.filter_by(user_id=escrow.provider_id).first()
        if not agent_wallet:
            agent_wallet = Wallet(user_id=escrow.provider_id, balance=Decimal("0.00"))
            db.session.add(agent_wallet)
        agent_wallet.balance += agent_amount  # Decimal + Decimal

        # Credit admin wallet (user_id=7)
        admin_wallet = Wallet.query.filter_by(user_id=7).first()
        if not admin_wallet:
            admin_wallet = Wallet(user_id=7, balance=Decimal("0.00"))
            db.session.add(admin_wallet)
        admin_wallet.balance += admin_amount

        # Record wallet transactions
        db.session.add(WalletTransaction(
            wallet_id=agent_wallet.id,
            user_id=escrow.provider_id,
            amount=agent_amount,
            transaction_type="credit",
            description=f"Escrow release from ID {escrow.id}",
            reference=str(uuid.uuid4())
        ))
        db.session.add(WalletTransaction(
            wallet_id=admin_wallet.id,
            user_id=7,
            amount=admin_amount,
            transaction_type="credit",
            description=f"Admin fee from escrow ID {escrow.id}",
            reference=str(uuid.uuid4())
        ))

        # Update escrow
        escrow.partial_release_amount = agent_amount
        escrow.amount_to_seller = agent_amount
        escrow.admin_fee = admin_amount
        escrow.is_released = True
        escrow.status = "released"
        escrow.released_at = datetime.utcnow()

        db.session.commit()
        flash(f"Released ₦{agent_amount} to Agent. Admin fee: ₦{admin_amount}.", "success")
        return redirect(url_for('seller_dashboard.my_dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        return redirect(url_for('seller_dashboard.my_dashboard'))




@seller_dashboard_bp.route('/pay_agent/<int:provider_id>', methods=['POST'])
@login_required
def pay_agent(provider_id):
    buyer = current_user
    amount = float(request.form.get("amount"))  # or however you pass it
    service_type = "agent"

    # 1. Get buyer wallet
    buyer_wallet = get_or_create_wallet(buyer.id)

    if buyer_wallet.balance < amount:
        flash("Insufficient balance", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # 2. Create escrow record
    escrow = EscrowPayment(
        buyer_id=buyer.id,
        provider_id=provider_id,
        amount=amount,
        type=service_type,
        status="pending"
    )
    db.session.add(escrow)
    db.session.flush()  # get escrow.id before commit

    # 3. Hold funds in escrow (wallet debit + transaction log)
    buyer_wallet.balance -= amount

    txn = WalletTransaction(
        wallet_id=buyer_wallet.id,
        user_id=buyer.id,
        related_escrow_id=escrow.id,  # link escrow
        amount=amount,
        transaction_type="escrow_hold",
        description=f"Escrow hold for {escrow.type}",
        reference=str(uuid.uuid4())
    )
    db.session.add(txn)
    db.session.commit()

    flash("Payment placed in escrow", "success")
    return redirect(url_for("seller_dashboard.my_dashboard"))

@seller_dashboard_bp.route("/transfer-to-escrow", methods=["POST"])
@login_required
def transfer_to_escrow():
    buyer = current_user
    provider_id = request.form.get("provider_id")   # agent/logistics selected
    amount = float(request.form.get("amount", 0))

    # 1. Find provider
    provider = User.query.filter_by(id=provider_id, is_escrow=True).first()

    if not provider:
        flash("No recipient found (provider is not escrow-enabled)", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # 2. Deduct from buyer wallet
    buyer_wallet = get_or_create_wallet(buyer.id)
    if buyer_wallet.balance < amount:
        flash("Insufficient funds", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    buyer_wallet.balance -= amount

    # 3. Lock money in Escrow table
    escrow = EscrowPayment(
        buyer_id=buyer.id,
        provider_id=provider.id,
        amount=amount,
        status="pending"
    )
    db.session.add(escrow)
    db.session.commit()

    flash(f"₦{amount} transferred to pending escrow for {provider.role.capitalize()}", "success")
    return redirect(url_for("seller_dashboard.my_dashboard"))


@seller_dashboard_bp.route("/escrow-status")
@login_required
def escrow_status():
    user = current_user

    # --- Product Escrow (normal purchase) ---
    product_escrows = EscrowPayment.query.filter_by(buyer_id=user.id).all()

    # --- Service Escrow (agent/logistics) ---
    service_escrows = EscrowPayment.query.filter_by(
        buyer_id=user.id,
        is_escrow=True
    ).all()

    return render_template(
        "escrow/status.html",
        product_escrows=product_escrows,
        service_escrows=service_escrows
    )

@seller_dashboard_bp.route('/complete-booking/<int:booking_id>', methods=['POST'])
@login_required
def complete_booking(booking_id):
    # Fetch the booking
    booking = BookingRequest.query.get_or_404(booking_id)

    # Ensure the current user is the assigned agent
    if current_user.id != booking.agent_id:
        flash("You are not authorized to complete this booking.", "danger")
        return redirect(url_for('seller_dashboard.booking_history'))

    # Ensure the booking is already confirmed by buyer
    if booking.status != 'buyer_confirmed':
        flash("Booking must be confirmed by the buyer before marking as completed.", "warning")
        return redirect(url_for('seller_dashboard.booking_history'))

    # Update status to completed
    booking.status = 'completed'
    db.session.commit()

    flash("Booking marked as completed successfully!", "success")
    return redirect(url_for('seller_dashboard.booking_history'))

@seller_dashboard_bp.route('/confirm-booking/<int:booking_id>', methods=['POST'])
@login_required
def confirm_booking(booking_id):
    booking = BookingRequest.query.get_or_404(booking_id)

    # Only the buyer can confirm
    if booking.buyer_id != current_user.id:
        abort(403)

    if booking.status != 'inspection_submitted':
        flash("This booking cannot be confirmed at this stage.", "warning")
        return redirect(url_for('seller_dashboard.booking_history'))

    # Update booking status
    booking.status = 'buyer_confirmed'
    booking.buyer_confirmed_at = datetime.utcnow()  # optional timestamp
    db.session.commit()

    # Notify agent and buyer via Socket.IO
    for user_id in [booking.agent_id, booking.buyer_id]:
        socketio.emit(
            'inspection_update',
            {
                'user_id': user_id,
                'message': f"Buyer has confirmed the inspection for booking #{booking.id}."
            },
            namespace='/notifications'
        )

    # Email notifications (same format as inspection submission)
    recipients = set()
    if booking.agent and booking.agent.email:
        recipients.add(booking.agent.email)
    if booking.buyer and booking.buyer.email:
        recipients.add(booking.buyer.email)

    for email in recipients:
        send_email(
            to=email,
            subject=f"Inspection Confirmed for Booking #{booking.id}",
            body=f"Dear user,\n\nThe buyer has confirmed the inspection for booking #{booking.id}.\nPlease review any further actions if needed.\n\nThank you."
        )

    flash("Booking confirmed successfully and notifications sent!", "success")
    return redirect(url_for('seller_dashboard.booking_history'))
  # adjust path based on where send_email is defined

@seller_dashboard_bp.route("/agent-withdraw", methods=["GET", "POST"])
@login_required
def agent_withdraw():
    # Ensure only agents can access
    if current_user.role != "agent":
        flash("Access denied.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # Get or create agent wallet
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    if not wallet:
        wallet = Wallet(user_id=current_user.id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()

    # Withdrawal form
    form = WithdrawalForm()

    # Agent's bank accounts
    bank_accounts = BankDetails.query.filter_by(user_id=current_user.id).all()
    form.bank_account.choices = [(b.id, f"{b.bank_name} - {b.account_number}") for b in bank_accounts]

    if request.method == "POST" and form.validate_on_submit():
        selected_bank = BankDetails.query.get(form.bank_account.data)
        amount = form.amount.data

        if not selected_bank:
            flash("Selected bank not found.", "danger")
            return redirect(url_for("seller_dashboard.agent_withdraw"))

        if amount > wallet.balance:
            flash("Insufficient balance.", "danger")
            return redirect(url_for("seller_dashboard.agent_withdraw"))

        # Initiate Paystack transfer
        transfer_result = initiate_paystack_transfer(
            bank_code=selected_bank.bank_code,
            account_number=selected_bank.account_number,
            amount=int(amount * 100),  # Paystack expects kobo
            name=selected_bank.account_name
        )

        if transfer_result.get("status"):
            wallet.balance -= amount
            db.session.commit()
            flash(f"Withdrawal of ₦{amount:,.2f} initiated successfully.", "success")
            return redirect(url_for("seller_dashboard.agent_withdraw"))
        else:
            flash("Withdrawal failed: " + transfer_result.get("message", "Unknown error"), "danger")

    return render_template(
        "wallet/agent_withdraw.html",  # Separate template for agent
        form=form,
        wallet=wallet,
        bank_accounts=bank_accounts
    )

# agents/routes.py
@seller_dashboard_bp.route("/agent/bank-details")
@login_required
def agent_bank_details():
    if current_user.role != "agent":
        abort(403)
    bank_accounts = BankDetails.query.filter_by(user_id=current_user.id).all()
    return render_template("agents/view_bank_details.html", bank_details=bank_accounts)

@seller_dashboard_bp.route("/agent/setup-payout", methods=["GET", "POST"])
@login_required
def agent_setup_payout():
    if current_user.role != "agent":
        abort(403)

    form = PayoutForm()
    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"
    }

    # Fetch banks from Paystack
    banks = []
    bank_response = requests.get("https://api.paystack.co/bank", headers=headers)
    if bank_response.status_code == 200:
        banks = bank_response.json().get("data", [])
        form.bank_name.choices = [(bank["code"], bank["name"]) for bank in banks]
    else:
        flash("Could not load banks", "danger")

    if form.validate_on_submit():
        bank_code = form.bank_name.data
        account_number = form.account_number.data
        account_name = form.account_name.data

        # Create Paystack recipient
        payload = {
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN"
        }
        response = requests.post("https://api.paystack.co/transferrecipient", json=payload, headers=headers)
        result = response.json()

        if result.get("status"):
            recipient_code = result["data"]["recipient_code"]

            # Create a new bank record (allow multiple accounts)
            bank_details = BankDetails(
                user_id=current_user.id,
                bank_name=dict(form.bank_name.choices).get(bank_code),
                bank_code=bank_code,
                account_number=account_number,
                account_name=account_name,
                recipient_code=recipient_code
            )
            db.session.add(bank_details)
            current_user.recipient_code = recipient_code
            db.session.commit()

            flash("Payout setup successful", "success")
            return redirect(url_for("seller_dashboard.agent_bank_details"))
        else:
            flash("Paystack Error: " + result.get("message", "Could not create recipient"), "danger")

    return render_template("agents/agent_payout.html", form=form, banks=banks)

@seller_dashboard_bp.route("/orders/<int:order_id>/review", methods=["POST"])
@login_required
def add_order_review(order_id):
    order = Order.query.get_or_404(order_id)

    # ✅ Ensure buyer is the one reviewing
    if current_user.id != order.buyer_id:
        flash("Only the buyer can review this order.", "danger")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order.id))

    # ✅ Must be completed
    if order.status != StatusEnum.completed:
        flash("You can only review after completing the order.", "warning")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order.id))

    # ✅ Prevent duplicate review
    existing = Review.query.filter_by(order_id=order.id, reviewer_id=current_user.id).first()
    if existing:
        flash("You already reviewed this order.", "info")
        return redirect(url_for("seller_dashboard.order_detail", order_id=order.id))

    # ✅ Save review
    review = Review(
        order_id=order.id,
        product_id=order.product_id,
        reviewer_id=current_user.id,
        reviewee_id=order.seller_id,
        rating=int(request.form['rating']),
        comment=request.form['comment']
    )
    db.session.add(review)
    db.session.commit()

    flash("Review submitted successfully.", "success")
    return redirect(url_for("seller_dashboard.order_detail", order_id=order.id))

from sqlalchemy import func

def get_product_rating(product_id):
    result = db.session.query(
        func.count(Review.id).label("total_reviews"),
        func.avg(Review.rating).label("average_rating")
    ).filter(Review.product_id == product_id).first()

    return result.total_reviews or 0, round(result.average_rating or 0, 1)