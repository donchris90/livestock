import os
import requests
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request,jsonify, redirect, url_for, flash, Response, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app.forms import RegistrationForm
from app.extensions import db
from app.utils.firebase_notifications import send_fcm_notification
from app.models import (User, Product,
                        WalletTransaction,AdminWalletTransaction,BookingRequest,Wallet,
                        AdminRevenue,VerificationDocument,AdminBroadcast, Setting,ChatMessage,
                        Subscription, Escrow, Payment,Withdrawal,EscrowPayment, BankDetails,ProfitHistory,AgentKYC, PlatformWallet,PromotionPayment)
from werkzeug.security import generate_password_hash
from flask_socketio import emit
from app.utils.paystack import create_transfer_recipient,initiate_paystack_transfer
import secrets
from app.utils.paystack import initialize_transaction



admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ✅ Restrict all admin routes
@admin_bp.before_request
def check_admin_login():
    if request.endpoint == 'admin.create_superadmin':
        return  # allow access without login
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))


# 🧾 Product Management
@admin_bp.route('/manage-products')
def manage_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/manage_products.html', products=products)


@admin_bp.route('/toggle-product-field/<int:product_id>/<string:field>', methods=['POST'])
def toggle_product_field(product_id, field):
    product = Product.query.get_or_404(product_id)

    if field == 'featured':
        product.is_featured = not product.is_featured
    elif field == 'boost':
        product.boost_score = 60 if product.boost_score <= 50 else 0

    db.session.commit()
    flash(f"{field.capitalize()} status updated for product ID {product_id}.", "success")
    return redirect(url_for('admin.manage_products'))


@admin_bp.route('/toggle-delete/<int:product_id>')
def toggle_delete(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_deleted = not product.is_deleted
    db.session.commit()
    flash(f"Product {'deleted' if product.is_deleted else 'restored'}.", "warning")
    return redirect(url_for("admin.manage_products"))


@admin_bp.route("/toggle-visibility/<int:product_id>")
def toggle_visibility(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_visible = not getattr(product, 'is_visible', True)
    db.session.commit()
    flash("Product visibility updated.", "info")
    return redirect(url_for("admin.manage_products"))


@admin_bp.route("/deleted-products")
def deleted_products():
    products = Product.query.filter_by(is_deleted=True).order_by(Product.updated_at.desc()).all()
    return render_template("admin/deleted_products.html", products=products)


@admin_bp.route("/flagged-products")
def flagged_products():
    flagged = Product.query.filter_by(is_flagged=True).all()
    return render_template("admin/flagged_products.html", products=flagged)


# 👥 User Management
@admin_bp.route("/manage-users")
def manage_users():
    # Get query parameters
    search_query = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()
    page = request.args.get("page", 1, type=int)

    # Base query
    query = User.query

    # Apply search
    if search_query:
        query = query.filter(
            or_(
                User.first_name.ilike(f"%{search_query}%"),
                User.last_name.ilike(f"%{search_query}%"),
                User.email.ilike(f"%{search_query}%")
            )
        )

    # Apply role filter
    if role_filter:
        query = query.filter_by(role=role_filter)

    # Order by newest users first and paginate
    users_pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=10)

    return render_template(
        "admin/manage_users.html",
        users=users_pagination
    )


@admin_bp.route('/toggle-user-verified/<int:user_id>', methods=['POST'])
def toggle_user_verified(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = not user.is_verified
    db.session.commit()
    flash("User verification status updated.", "success")
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/toggle-user-active/<int:user_id>', methods=['POST'])
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f"User {'activated' if user.is_active else 'suspended'}.", "info")
    return redirect(url_for('admin.manage_users'))


@admin_bp.route("/add-user-note/<int:user_id>", methods=["POST"])
def add_user_note(user_id):
    user = User.query.get_or_404(user_id)
    note = request.form.get("note")
    user.admin_note = note
    db.session.commit()
    flash("Note added to user.", "info")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route('/bulk-action', methods=['POST'])
def bulk_action():
    selected_ids = request.form.getlist('selected_users')
    action = request.form.get('action')

    if not selected_ids or not action:
        flash("Please select users and an action.", "warning")
        return redirect(url_for('admin.manage_users'))

    users = User.query.filter(User.id.in_(selected_ids)).all()
    for user in users:
        if action == 'verify':
            user.is_verified = True
        elif action == 'unverify':
            user.is_verified = False
        elif action == 'suspend':
            user.is_active = False
        elif action == 'activate':
            user.is_active = True

    db.session.commit()
    flash(f"{action.capitalize()} applied to selected users.", "success")
    return redirect(url_for('admin.manage_users'))


@admin_bp.route("/export-users-csv")
def export_users_csv():
    users = User.query.order_by(User.created_at.desc()).all()

    def generate():
        data = [["ID", "Name", "Email", "Role", "State", "City", "Verified", "Status", "Joined"]]
        for u in users:
            data.append([
                u.id,
                f"{u.first_name} {u.last_name}",
                u.email,
                u.role,
                u.state,
                u.city,
                "Yes" if u.is_verified else "No",
                "Active" if u.is_active else "Suspended",
                u.created_at.strftime("%Y-%m-%d"),
            ])
        return "\n".join([",".join(map(str, row)) for row in data])

    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=users.csv"})


# 📊 Admin Dashboard
@admin_bp.route('/dashboard')
@login_required
def admin_dashboard():
    today = datetime.utcnow().date()
    last_7_days = [(today - timedelta(days=i)) for i in reversed(range(7))]

    # All payments for admin revenue
    payments = Payment.query.order_by(Payment.created_at.desc()).all()
    admin_revenue = sum(p.admin_fee or 0 for p in payments)

    # Escrow Wallet = Total funds in 'paid' status but not yet released to seller
    escrow_wallet = db.session.query(func.coalesce(func.sum(EscrowPayment.total_amount), 0)).filter(
        EscrowPayment.status == 'paid',
        EscrowPayment.seller_paid == False,
        EscrowPayment.is_deleted == False
    ).scalar()

    # Released Wallet = Funds marked complete but not yet paid to seller
    released_wallet = db.session.query(func.coalesce(func.sum(EscrowPayment.total_amount), 0)).filter(
        EscrowPayment.status == 'completed',
        EscrowPayment.seller_paid == False,
        EscrowPayment.is_deleted == False
    ).scalar()

    # Subscription revenue
    subscription_wallet = db.session.query(
        func.coalesce(func.sum(Subscription.amount), 0)
    ).filter(Subscription.status == "success").scalar()

    # Promotion revenue
    promotion_wallet = db.session.query(
        func.coalesce(func.sum(PromotionPayment.price), 0)
    ).filter(PromotionPayment.status == "paid").scalar()

    # Admin wallet balance from transactions
    credits = db.session.query(func.coalesce(func.sum(WalletTransaction.amount), 0)).filter_by(transaction_type='credit').scalar()
    debits = db.session.query(func.coalesce(func.sum(WalletTransaction.amount), 0)).filter_by(transaction_type='debit').scalar()
    admin_wallet_balance = credits - debits

    # Admin commission from Escrow
    commission_wallet = db.session.query(func.coalesce(func.sum(EscrowPayment.escrow_fee), 0)).scalar()

    # Total admin revenue
    total_admin_revenue = promotion_wallet + subscription_wallet + commission_wallet

    # All escrow orders that are not deleted
    escrow_orders = EscrowPayment.query.filter(EscrowPayment.is_deleted == False).order_by(EscrowPayment.id.desc()).all()

    # Pending escrows for display (list)
    pending_escrows = EscrowPayment.query.filter(EscrowPayment.status != 'released').all()

    # Current admin wallet
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    balance = wallet.balance if wallet else 0

    return render_template(
        "admin/dashboard.html",
        escrow_wallet=escrow_wallet,
        released_wallet=released_wallet,
        escrows=pending_escrows,      # Pass as list to template
        balance=balance,
        subscription_wallet=subscription_wallet,
        admin_wallet_balance=admin_wallet_balance,
        commission_wallet=commission_wallet,
        promotion_wallet=promotion_wallet,
        escrow_orders=escrow_orders,
        total_admin_revenue=total_admin_revenue,

        user_count=User.query.count(),
        product_count=Product.query.count(),
        booking_count=BookingRequest.query.count(),

        verified_sellers=User.query.filter_by(is_verified=True).count(),
        suspended_users=User.query.filter_by(is_active=False).count(),
        flagged_users=User.query.filter_by(is_flagged=True).count(),

        flagged_products=Product.query.filter_by(is_flagged=True).count(),
        featured_count=Product.query.filter_by(is_featured=True).count(),
        boosted_count=Product.query.filter(Product.boost_score > 50).count(),

        recent_users=User.query.order_by(User.created_at.desc()).limit(5).all(),
        recent_products=Product.query.order_by(Product.created_at.desc()).limit(5).all(),

        pending_bookings=BookingRequest.query.filter_by(status="pending").count(),
        completed_bookings=BookingRequest.query.filter_by(status="completed").count(),

        total_messages=ChatMessage.query.count(),
        active_chats=db.session.query(ChatMessage.sender_id).distinct().count(),

        subscription_stats=db.session.query(
            Subscription.plan_name, func.count().label("count")
        ).group_by(Subscription.plan_name).all(),

        user_roles=['buyer', 'seller', 'agent', 'vet', 'logistics'],
        user_role_counts=[
            User.query.filter_by(role=r).count()
            for r in ['buyer', 'seller', 'agent', 'vet', 'logistics']
        ],

        product_status_counts=[
            Product.query.filter_by(is_featured=True).count(),
            Product.query.filter(Product.boost_score > 50).count(),
            Product.query.count() -
            Product.query.filter_by(is_featured=True).count() -
            Product.query.filter(Product.boost_score > 50).count()
        ],

        weekly_labels=[d.strftime('%a') for d in last_7_days],
        weekly_signups=[
            User.query.filter(func.date(User.created_at) == d).count()
            for d in last_7_days
        ],

        payments=payments,
        admin_revenue=admin_revenue
    )

@admin_bp.route("/revenue-dashboard")
@login_required  # if admin is logged in
def revenue_dashboard():
    subscription_wallet = db.session.query(
        func.coalesce(func.sum(Subscription.price), 0)
    ).filter(Subscription.status == "success").scalar()

    subscription_stats = db.session.query(
        Subscription.plan_name,
        func.count().label("count")
    ).filter(Subscription.status == "success").group_by(Subscription.plan_name).all()

    return render_template("admin/revenue_dashboard.html",
                           subscription_wallet=subscription_wallet,
                           subscription_stats=subscription_stats)


@admin_bp.route("/register", methods=["GET", "POST"])
@login_required
def admin_register():
    if not current_user.is_admin:
        abort(403)

    form = RegistrationForm()

    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash("Email already registered.", "danger")
            return redirect(url_for("admin.admin_register"))

        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data),
            role="admin",  # Explicitly mark as admin
            is_admin=True,
            is_active=True,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        flash("Admin account created successfully.", "success")
        return redirect(url_for("admin.manage_users"))

    return render_template("admin/admin_register.html", form=form)

@admin_bp.route('/create-superadmin', methods=['GET', 'POST'])
def create_superadmin():
    from werkzeug.security import generate_password_hash
    from app.models import User
    from app.extensions import db

    existing_admin = User.query.filter_by(is_admin=True).first()
    if existing_admin:
        return "Admin already exists. Remove this route.", 403

    admin = User(
        first_name="Super",
        last_name="Admin",
        email="admin@example.com",
        role="admin",
        is_admin=True,
        is_verified=True,
        is_active=True,
        password_hash=generate_password_hash("happen123"),

        # Provide required non-null fields:
        state="Lagos",
        city="Ikeja",
        street="Admin Street",
        phone="0000000000"
    )
    db.session.add(admin)
    db.session.commit()

    return "✅ Super admin created! You can now login and delete this route."
@admin_bp.route('/flagged-users')
def flagged_users():
    # Fetch and render flagged users
    users = User.query.filter_by(is_flagged=True).all()
    return render_template('admin/flagged_users.html', users=users)

@admin_bp.route('/manage-vets')
def manage_vets():
    vets = User.query.filter_by(role='vet').all()
    return render_template('admin/manage_vets.html', vets=vets)

@admin_bp.route('/manage-logistics')
def manage_logistics():
    logistics = User.query.filter_by(role='logistics').all()
    return render_template('admin/manage_logistics.html', logistics=logistics)

@admin_bp.route('/reviews')
def reviews():
    from app.models import Review  # or import at top
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template('admin/reviews.html', reviews=reviews)

@admin_bp.route('/reports')
def reports():
    # You can customize the data below
    return render_template('admin/reports.html')

@admin_bp.route('/notifications')
def notifications():
    # Sample placeholder
    return render_template('admin/notifications.html')

@admin_bp.route('/settings')
def settings():
    return render_template('admin/settings.html')

@admin_bp.route('/verify-user/<int:user_id>', methods=['POST'])
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    db.session.commit()
    flash(f'User {user.first_name} verified successfully.', 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/suspend-user/<int:user_id>', methods=['POST'])
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False  # or user.status = 'suspended'
    db.session.commit()
    flash(f"{user.first_name} has been suspended.", "danger")
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/unverify-user/<int:user_id>', methods=['POST'])
def unverify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = False  # Assuming you have this field in your User model
    db.session.commit()
    flash(f"{user.first_name} has been unverified.", "warning")
    return redirect(url_for('admin.manage_users'))

# routes/admin.py or wherever your admin routes are
@admin_bp.route('/subscriptions')
def admin_subscriptions():
    from app.models import User
    selected_plan = request.args.get('plan', 'all')

    # If filtering for a specific plan
    if selected_plan != 'all':
        users = User.query.join(User.subscription).filter_by(plan=selected_plan).order_by(User.created_at.desc()).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()

    return render_template('admin/subscriptions.html', users=users, selected_plan=selected_plan)

@admin_bp.route('/toggle_boost/<int:product_id>')
def toggle_boost(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_boosted = not product.is_boosted
    db.session.commit()
    flash("🚀 Boost status updated.", "success")
    return redirect(request.referrer or url_for('admin.manage_products'))

@admin_bp.route('/toggle_top/<int:product_id>')
def toggle_top(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_top = not product.is_top
    db.session.commit()
    flash("🏆 Top status updated.", "success")
    return redirect(request.referrer or url_for('admin.manage_products'))

# promotion/routes.py

@admin_bp.route('/promotion-success/<int:product_id>', methods=['GET'])
def promotion_success(product_id):
    product = Product.query.get_or_404(product_id)

    # Apply the promotion
    product.is_featured = True
    product.is_boosted = True
    product.boost_expiry = datetime.utcnow() + timedelta(days=30)  # customize duration

    db.session.commit()
    flash("🎉 Promotion applied: product is now featured and boosted.", "success")
    return redirect(url_for('seller_dashboard.my_products'))

@admin_bp.route('/escrows')
@login_required
def view_escrows():
    escrows = Escrow.query.order_by(Escrow.created_at.desc()).all()
    return render_template('admin/escrows.html', escrows=escrows)

@admin_bp.route('/payments')
@login_required
def all_payments():
    if not current_user.is_admin:
        abort(403)

    filter_type = request.args.get('filter')
    if filter_type == 'refunds':
        payments = Payment.query.filter_by(refund_requested=True).order_by(Payment.created_at.desc()).all()
    else:
        payments = Payment.query.order_by(Payment.created_at.desc()).all()

    return render_template('admin/payments.html', payments=payments, filter_type=filter_type)


@admin_bp.route('/approve-refund/<int:payment_id>', methods=['POST'])
@login_required
def approve_refund(payment_id):
    if not current_user.is_admin:
        abort(403)

    payment = Payment.query.get_or_404(payment_id)

    if payment.status == 'success' and payment.refund_requested:
        payment.status = 'refunded'
        payment.refund_requested = False

        user = payment.user
        user.plan_name = 'Free'
        user.upload_limit = 2
        user.grace_end = None

        # Log refund
        refund_log = RefundLog(payment_id=payment.id, admin_id=current_user.id)
        db.session.add(refund_log)

        # Optional: Send email
        # send_email(to=user.email, subject="Your refund was approved", ...)

        db.session.commit()
        flash('Refund approved and logged.', 'success')
    else:
        flash('Invalid refund request.', 'warning')

    return redirect(url_for('admin.all_payments'))

@admin_bp.route("/escrow/mark-complete/<int:escrow_id>", methods=["POST"])
@login_required
def mark_escrow_complete(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)
    escrow.is_completed = True
    escrow.is_disbursed = True
    db.session.commit()
    flash("Escrow marked as completed and disbursed.", "success")
    return redirect(url_for("admin.view_escrow_payments"))

@admin_bp.route("/admin-revenue")
@login_required  # optional: add @admin_required if role-based
def admin_revenue():
    revenues = AdminRevenue.query.order_by(AdminRevenue.created_at.desc()).all()
    return render_template("admin/admin_revenue.html", revenues=revenues)

@admin_bp.route("/admin-settings", methods=["GET", "POST"])
@login_required  # Optional: restrict to only logged-in admin users
def admin_settings():
    if request.method == "POST":
        for key, value in request.form.items():
            if key == 'csrf_token':  # Skip CSRF field
                continue

            setting = Setting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                setting = Setting(key=key, value=value)
                db.session.add(setting)
        db.session.commit()
        flash("Settings updated successfully", "success")
        return redirect(url_for("admin_bp.admin_settings"))

    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/admin_settings.html", settings=settings)



@admin_bp.route("/admin/escrow-overview")
@login_required
def escrow_overview():
    # Escrow Wallet (funds held in escrow but not yet released)
    escrow_wallet = db.session.query(func.sum(EscrowPayment.total_amount)).filter(
        EscrowPayment.status == 'paid',
        EscrowPayment.seller_paid == False
    ).scalar() or 0.0

    # Released Funds (marked complete, available for withdrawal)
    released_wallet = db.session.query(func.sum(EscrowPayment.total_amount)).filter(
        EscrowPayment.status == 'completed',
        EscrowPayment.seller_paid == False
    ).scalar() or 0.0

    # Commission Revenue (e.g., % of transactions)
    commission_wallet = db.session.query(func.sum(EscrowPayment.commission_amount)).scalar() or 0.0

    # Subscription Revenue
    subscription_wallet = db.session.query(func.sum(Subscription.amount)).scalar() or 0.0

    return render_template("admin/escrow_overview.html",
        escrow_wallet=escrow_wallet,
        released_wallet=released_wallet,
        commission_wallet=commission_wallet,
        subscription_wallet=subscription_wallet
    )


from datetime import datetime


from decimal import Decimal
from flask import flash, redirect, request
from datetime import datetime

from decimal import Decimal, ROUND_DOWN

@admin_bp.route('/mark-order-complete/<int:escrow_id>', methods=['POST'])
@login_required
def admin_mark_complete(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    if escrow.status != "paid":
        flash("Escrow payment not yet made", "warning")
        return redirect(request.referrer)

    if escrow.order_completed:
        flash("This order has already been marked as completed.", "info")
        return redirect(request.referrer)

    # ✅ Use provider (not seller_id)
    seller = escrow.provider
    admin_user = User.query.filter_by(role='admin').first()

    if not seller:
        flash("Seller account not found.", "danger")
        return redirect(request.referrer)

    if not admin_user:
        flash("Admin user not found.", "danger")
        return redirect(request.referrer)

    try:
        total_amount = Decimal(escrow.total_amount or 0).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        escrow_fee = (total_amount * Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        offer_amount = (total_amount - escrow_fee).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

        # Credit seller
        seller.wallet_balance = Decimal(seller.wallet_balance or 0) + offer_amount
        seller_wallet = Wallet.query.filter_by(user_id=seller.id).first()
        if not seller_wallet:
            flash("Seller wallet not found.", "danger")
            return redirect(request.referrer)

        admin_wallet = Wallet.query.filter_by(user_id=admin_user.id).first()
        if not admin_wallet:
            flash("Admin wallet not found.", "danger")
            return redirect(request.referrer)

        # Seller wallet transaction
        seller_txn = WalletTransaction(
            user_id=seller.id,
            wallet_id=seller_wallet.id,
            amount=offer_amount,
            transaction_type="credit",
            description=f"Escrow payout for product: {escrow.product.title if escrow.product else 'N/A'}",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            status="success",
            related_escrow_id=escrow.id,
        )
        db.session.add(seller_txn)

        # Admin wallet transaction
        if escrow_fee > 0:
            admin_user.wallet_balance = Decimal(admin_user.wallet_balance or 0) + escrow_fee

            admin_txn = WalletTransaction(
                user_id=admin_user.id,
                wallet_id=admin_wallet.id,
                amount=escrow_fee,
                transaction_type="credit",
                description=f"Escrow fee earned for product: {escrow.product.title if escrow.product else 'N/A'}",
                timestamp=datetime.utcnow(),
                created_at=datetime.utcnow(),
                status="success",
                related_escrow_id=escrow.id,
            )
            db.session.add(admin_txn)

        # Update escrow status
        escrow.order_completed = True
        escrow.released_at = datetime.utcnow()

        db.session.commit()
        flash("Escrow released successfully. Seller and Admin wallets updated.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error during payout release: {str(e)}", "danger")

    return redirect(request.referrer)


@admin_bp.route("/admin-escrow-orders")
@login_required
  # Optional: protect with a decorator
def admin_escrow_dashboard():
    escrows = EscrowPayment.query.order_by(EscrowPayment.id.desc()).all()
    return render_template("admin/escrow_orders.html", escrows=escrows)


from datetime import datetime

@admin_bp.route('/release-fund/<int:escrow_id>', methods=['POST'])
@login_required
def release_fund(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    # 🔐 Check if current user is admin
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # ✅ Fetch admin wallet
    admin_user = User.query.filter_by(role='admin').first()
    if not admin_user:
        flash("Admin user not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    admin_wallet = Wallet.query.filter_by(user_id=admin_user.id).first()
    if not admin_wallet:
        flash("Admin wallet not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    # 🧾 Fetch seller wallet
    seller_wallet = Wallet.query.filter_by(user_id=escrow.seller_id).first()
    if not seller_wallet:
        flash("Seller wallet not found.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    # 💸 Fund Split
    amount_offer = escrow.offer_amount
    escrow_fee = escrow.escrow_fee or 0

    seller_wallet.balance += amount_offer
    admin_wallet.balance += escrow_fee

    escrow.status = "released"
    escrow.released_by_admin = True
    escrow.released_at = datetime.utcnow()

    db.session.commit()

    flash("Funds released and split successfully.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/revenue-overview")
@login_required  # Optional: protect it
def revenue_overview():
    from sqlalchemy import func

    total_profit = db.session.query(func.sum(ProfitHistory.amount)).scalar() or 0

    profit_breakdown = db.session.query(
        ProfitHistory.source_type,
        func.sum(ProfitHistory.amount)
    ).group_by(ProfitHistory.source_type).all()

    wallet = PlatformWallet.query.get(1)

    return render_template("admin/revenue_overview.html",
                           total_profit=total_profit,
                           profit_breakdown=profit_breakdown,
                           wallet=wallet)

@admin_bp.route("/admin/revenue")
@login_required
def platform_revenue():
    wallet = PlatformWallet.query.get(1) or PlatformWallet(id=1)
    profit_logs = ProfitHistory.query.order_by(ProfitHistory.created_at.desc()).all()

    return render_template(
        "admin/revenue.html",
        wallet=wallet,
        total_profit=sum(p.amount for p in profit_logs),
        profit_logs=profit_logs
    )

@admin_bp.route('/kyc/<int:kyc_id>', methods=['GET', 'POST'])
@login_required
def approve_kyc_detail(kyc_id):
    kyc = AgentKYC.query.get_or_404(kyc_id)

    if request.method == 'POST':
        action = request.form.get('action')  # 'approve' or 'reject'
        if action in ['approved', 'reject']:
            kyc.status = action
            db.session.commit()
            flash(f'KYC has been {action}d.', 'success')
            return redirect(url_for('admin.list_kyc'))

    return render_template('admin/approve_kyc_detail.html', kyc=kyc)


@admin_bp.route("/approve_kyc/<int:kyc_id>", methods=["POST"])
@login_required
def approve_kyc(kyc_id):
    kyc = AgentKYC.query.get_or_404(kyc_id)
    action = request.form.get("action")
    if action == "approved":
        kyc.status = "approved"
    elif action == "reject":
        kyc.status = "rejected"
    db.session.commit()
    flash(f"KYC {action}d successfully.", "success")
    return redirect(url_for("admin.list_kyc"))



@admin_bp.route("/reject_kyc/<int:kyc_id>", methods=["POST"])
@login_required
def reject_kyc(kyc_id):
    if current_user.role != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    kyc = AgentKYC.query.get_or_404(kyc_id)
    kyc.status = "rejected"
    kyc.user.is_verified = False
    db.session.commit()

    flash("KYC rejected successfully!", "warning")
    return redirect(url_for("admin.admin_dashboard"))

@admin_bp.route("/list_kyc")
@login_required
def list_kyc():
    """Display all agent KYC requests."""
    kycs = AgentKYC.query.order_by(AgentKYC.created_at.desc()).all()
    return render_template("admin/adminkyc.html", kycs=kycs)

# Menu Link: Seller KYC List
@admin_bp.route("/seller-kyc-list")
@login_required
def seller_kyc_list():
    # Fetch all seller KYC documents, grouped by user
    kycs = VerificationDocument.query.join(User).filter(User.role == 'seller').order_by(VerificationDocument.id.desc()).all()
    return render_template("admin/seller_kyc_list.html", kycs=kycs)


# View Individual Seller KYC
@admin_bp.route("/seller-kyc/<int:user_id>")
@login_required
def view_seller_kyc(user_id):
    seller = User.query.get_or_404(user_id)
    documents = VerificationDocument.query.filter_by(user_id=user_id).all()
    return render_template("admin/seller_kyc_detail.html", seller=seller, documents=documents)


# Approve or Reject a Seller KYC
@admin_bp.route("/seller-kyc/<int:user_id>/action/<string:action>", methods=["POST"])
@login_required
def seller_kyc_action(user_id, action):
    seller = User.query.get_or_404(user_id)
    kycs = VerificationDocument.query.filter_by(user_id=user_id).all()

    if action not in ["approve", "reject"]:
        flash("Invalid action", "danger")
        return redirect(url_for("admin.view_seller_kyc", user_id=user_id))

    for kyc in kycs:
        kyc.status = "approved" if action == "approve" else "rejected"
    db.session.commit()

    flash(f"Seller KYC {action}d successfully.", "success")
    return redirect(url_for("admin.seller_kyc_list"))

# List all pending withdrawals
@admin_bp.route("/withdrawals")
@login_required
def list_withdrawals():
    pending_withdrawals = Withdrawal.query.filter_by(status="pending").order_by(Withdrawal.requested_at.desc()).all()
    return render_template("admin/withdrawals.html", withdrawals=pending_withdrawals)

# Approve a withdrawal
from app.utils.paystack import create_transfer_recipient, initiate_paystack_transfer

@admin_bp.route("/withdrawals/approve/<int:withdrawal_id>")
@login_required
def approve_withdrawal(withdrawal_id):
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    if withdrawal.status != "pending":
        flash("Withdrawal already processed.", "warning")
        return redirect(url_for("admin.list_withdrawals"))

    # Get bank details
    bank = withdrawal.bank
    if not bank:
        flash("Bank account not found.", "danger")
        return redirect(url_for("admin.list_withdrawals"))

    # Create transfer recipient in Paystack
    recipient_data = create_transfer_recipient(
        name=bank.account_name,
        account_number=bank.account_number,
        bank_code=bank.bank_code
    )

    if not recipient_data:
        flash("Failed to create Paystack recipient.", "danger")
        return redirect(url_for("admin.list_withdrawals"))

    recipient_code = recipient_data["recipient_code"]

    # ✅ Corrected function call
    transfer_result = initiate_paystack_transfer(
        int(withdrawal.amount * 100),  # amount in kobo
        recipient_code,
        reason="Withdrawal Payout"
    )

    if transfer_result.get("status"):
        withdrawal.status = "approved"
        withdrawal.processed_at = datetime.utcnow()
        db.session.commit()
        flash(f"Withdrawal of ₦{withdrawal.amount:,.2f} approved and processed.", "success")
    else:
        flash("Transfer failed: " + transfer_result.get("message", "Unknown error"), "danger")

    return redirect(url_for("admin.list_withdrawals"))



# Reject a withdrawal
@admin_bp.route("/withdrawals/reject/<int:withdrawal_id>")
@login_required
def reject_withdrawal(withdrawal_id):
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    if withdrawal.status != "pending":
        flash("Withdrawal already processed.", "warning")
        return redirect(url_for("admin.list_withdrawals"))

    # Refund amount to wallet
    wallet = Wallet.query.filter_by(user_id=withdrawal.user_id).first()
    if wallet:
        wallet.balance += withdrawal.amount

    withdrawal.status = "rejected"
    withdrawal.processed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Withdrawal of ₦{withdrawal.amount:,.2f} rejected and refunded.", "info")

    return redirect(url_for("admin.list_withdrawals"))

# admin/routes.py
@admin_bp.route('/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast_message():
    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')

        if not title or not message:
            flash("Both title and message are required", "danger")
            return redirect(url_for('admin.broadcast_message'))

        new_msg = AdminBroadcast(title=title, message=message)
        db.session.add(new_msg)
        db.session.commit()

        flash("Broadcast message sent successfully!", "success")
        return redirect(url_for('admin.broadcast_message'))

    return render_template('admin/admin_broadcast.html')

@admin_bp.route('/api/admin-messages', methods=['GET'])
def admin_messages():
    messages = AdminBroadcast.query.order_by(AdminBroadcast.created_at.desc()).all()
    return jsonify([msg.to_dict() for msg in messages])
