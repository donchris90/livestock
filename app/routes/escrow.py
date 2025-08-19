import os
import uuid
import requests
from decimal import Decimal
from datetime import datetime
from flask import current_app
from sqlalchemy import func
from app.forms import OfferForm,OfferAmountForm,CreateOrderForm
from app.utils.payout_utils import get_or_create_wallet,get_admin_wallet
from sqlalchemy import Enum
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, abort,session,jsonify
)
from flask_login import login_required, current_user
from app.utils.paystack import transfer_funds_to_seller,create_and_transfer_to_recipient
from flask_socketio import SocketIO, emit, join_room, leave_room
from app.utils.paystack import initialize_transaction

from app.models import Product, EscrowPayment, EscrowAudit,Notification,Order,User,Wallet,PlatformWallet,ProfitHistory,PaymentStatus,OrderStatus,StatusEnum
from app.extensions import db
from app import socketio
from app.forms import EscrowPaymentForm
from app.utils.paystack_utils import verify_paystack_transaction
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
from app.utils.paystack import verify_paystack_payment

escrow_bp = Blueprint('escrow', __name__, url_prefix='/escrow')

def get_admin_account():
    return User.query.filter_by(role="admin").first()

def generate_reference():
    return str(uuid.uuid4()).replace('-', '')[:15]


# --- Buyer marks as Paid (funds go to escrow) ---
@escrow_bp.route('/mark-as-paid/<int:escrow_id>', methods=['POST'])
@login_required
def mark_as_paid(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    if escrow.buyer_id != current_user.id:
        flash("You cannot mark this escrow as paid.", "danger")
        return redirect(url_for('escrow.my_escrows'))

    if escrow.is_paid:
        flash("Escrow is already marked as paid.", "warning")
        return redirect(url_for('escrow.my_escrows'))

    escrow.is_paid = True
    escrow.status = 'paid'
    escrow.paid_at = datetime.utcnow()
    db.session.commit()

    flash("Payment recorded in escrow. Funds are held until order completion.", "success")
    return redirect(url_for('escrow.my_escrows'))


@escrow_bp.route('/complete-order/<int:escrow_id>', methods=['POST'])
@login_required
def complete_order(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    if escrow.status in ["completed", "cancelled"]:
        flash("Escrow already completed or cancelled.", "warning")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    try:
        # Seller amount = full offer
        seller_amount = Decimal(str(escrow.base_amount))

        # Admin fee (3% of seller offer)
        admin_rate = Decimal("0.03")
        admin_fee = (seller_amount * admin_rate).quantize(Decimal("0.01"))

        # Credit seller wallet
        seller_wallet = Wallet.query.filter_by(user_id=escrow.seller_id).first()
        if not seller_wallet:
            seller_wallet = Wallet(user_id=escrow.seller_id, balance=Decimal("0.00"))
            db.session.add(seller_wallet)
        seller_wallet.balance += seller_amount

        # Credit admin wallet (user_id=7)
        admin_wallet = Wallet.query.filter_by(user_id=7).first()
        if not admin_wallet:
            admin_wallet = Wallet(user_id=7, balance=Decimal("0.00"))
            db.session.add(admin_wallet)
        admin_wallet.balance += admin_fee

        escrow.status = "completed"
        escrow.completed_at = datetime.utcnow()
        escrow.seller_paid = True

        db.session.commit()

        flash(
            f"Payment of ₦{(seller_amount + admin_fee):.2f} released. "
            f"Seller gets ₦{seller_amount:.2f}, Admin fee ₦{admin_fee:.2f}.",
            "success"
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Error completing escrow: {str(e)}", "danger")

    return redirect(url_for("seller_dashboard.my_dashboard"))





# --- View Escrows (Buyer & Seller) ---
@escrow_bp.route('/my-escrows')
@login_required
def my_escrows():
    user_id = current_user.id

    # Buyer escrows
    buyer_escrows = EscrowPayment.query.filter_by(buyer_id=user_id).all()

    # Seller escrows
    seller_escrows = EscrowPayment.query.filter_by(seller_id=user_id).all()

    # Totals for display
    buyer_locked_total = sum(e.amount for e in buyer_escrows if e.status == 'locked')
    seller_locked_total = sum(e.amount for e in seller_escrows if e.status == 'locked')

    return render_template(
        'escrow/view_escrow.html',
        buyer_escrows=buyer_escrows,
        seller_escrows=seller_escrows,
        buyer_locked_total=buyer_locked_total,
        seller_locked_total=seller_locked_total
    )



# --- Paystack verification ---
@escrow_bp.route('/verify-payment/<int:escrow_id>')
@login_required
def verify_payment(escrow_id):
    reference = request.args.get("reference")
    if not reference:
        flash("Payment reference is missing.", "danger")
        return redirect(url_for("escrow.my_escrows"))

    headers = {"Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"}
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    response = requests.get(verify_url, headers=headers)

    if response.status_code != 200:
        flash("Unable to verify payment. Try again.", "danger")
        return redirect(url_for("escrow.my_escrows"))

    data = response.json()
    if not (data["status"] and data["data"]["status"] == "success"):
        flash("Payment verification failed.", "danger")
        return redirect(url_for("escrow.my_escrows"))

    try:
        escrow = EscrowPayment.query.get_or_404(escrow_id)
        if escrow.is_paid:
            flash("Payment already verified.", "info")
            return redirect(url_for("escrow.my_escrows"))

        # Paystack returns amount in kobo, convert to Naira
        total_paid = Decimal(str(data["data"]["amount"])) / 100

        # Seller offer is base_amount or offer_amount
        seller_offer = Decimal(str(escrow.base_amount or escrow.offer_amount or total_paid))

        # Admin fee = total paid - seller offer
        admin_fee = total_paid - seller_offer

        # Update escrow only (do not credit seller wallet yet)
        escrow.is_paid = True
        escrow.status = "paid"
        escrow.payment_reference = reference
        escrow.paid_at = datetime.utcnow()
        escrow.total_amount = total_paid
        escrow.seller_amount = seller_offer
        escrow.admin_fee = admin_fee

        db.session.commit()
        flash(f"Payment verified. Funds held in escrow: Seller ₦{seller_offer}, Admin fee ₦{admin_fee}.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error verifying payment: {str(e)}", "danger")

    return redirect(url_for("escrow.my_escrows"))


@escrow_bp.route("/mark-complete/<int:escrow_id>", methods=["POST"])
@login_required
def mark_complete(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    # Only the buyer or admin can mark complete
    is_buyer = escrow.buyer_id == current_user.id
    is_admin = current_user.role == 'admin'

    if not (is_buyer or is_admin):
        flash("You are not authorized to complete this transaction.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # Escrow must be paid first
    if escrow.status != "paid":
        flash("This transaction cannot be completed before payment.", "warning")
        return redirect(url_for("escrow.my_escrows"))

    # Get wallets
    seller_wallet = Wallet.query.filter_by(user_id=escrow.seller_id).first()
    if not seller_wallet:
        seller_wallet = Wallet(user_id=escrow.seller_id, balance=0.0)
        db.session.add(seller_wallet)

    admin_user = User.query.filter_by(role='admin').first()
    admin_wallet = Wallet.query.filter_by(user_id=admin_user.id).first()
    if not admin_wallet:
        admin_wallet = Wallet(user_id=admin_user.id, balance=0.0)
        db.session.add(admin_wallet)

    # Release funds
    seller_wallet.balance += escrow.offer_amount
    admin_wallet.balance += escrow.escrow_fee or 0

    # Update escrow
    escrow.status = "completed"
    escrow.is_released = True
    escrow.completed_at = datetime.utcnow()
    escrow.buyer_marked_complete = is_buyer
    escrow.marked_by_admin = is_admin
    escrow.marked_by_user_id = current_user.id

    db.session.commit()

    flash("✅ Transaction marked as complete! Funds have been released to the seller.", "success")
    return redirect(url_for("escrow.my_escrows"))

from app.forms import OfferForm
@escrow_bp.route("/submit-offer/<int:product_id>", methods=["GET", "POST"])
@login_required
def escrow_offer(product_id):
    product = Product.query.get_or_404(product_id)
    seller = User.query.get_or_404(product.user_id)
    form = OfferForm()

    # Get the last completed escrow for this buyer & product
    last_completed_escrow = EscrowPayment.query.filter_by(
        buyer_id=current_user.id,
        product_id=product.id,
        status='completed'
    ).order_by(EscrowPayment.created_at.desc()).first()

    # Check for any active/pending escrow
    active_escrow = EscrowPayment.query.filter_by(
        buyer_id=current_user.id,
        product_id=product.id,
        is_paid=False,
        status='pending'
    ).first()

    if active_escrow:
        flash("You already have a pending escrow for this product. Complete it before making a new offer.", "warning")
        return redirect(url_for('escrow.my_escrows'))

    if form.validate_on_submit():
        base_amount = form.offer_amount.data

        # Optional escrow fee (3%)
        escrow_fee = (base_amount * Decimal('0.03')).quantize(Decimal('0.01'))
        total_amount = (base_amount + escrow_fee).quantize(Decimal('0.01'))

        # Create new escrow record
        new_escrow = EscrowPayment(
            buyer_id=current_user.id,
            seller_id=product.user_id,
            provider_id=product.user_id,
            product_id=product.id,
            base_amount=base_amount,
            escrow_fee=escrow_fee,
            amount=base_amount,
            total_amount=total_amount,
            offer_amount=base_amount,
            status='pending',
            is_paid=False,
            is_released=False,
            reference=str(uuid.uuid4()),
            buyer_name=current_user.full_name,
            seller_name=seller.full_name,
            type='product'
        )
        db.session.add(new_escrow)
        db.session.commit()

        flash("Offer submitted! Click Pay button below to complete payment.", "success")
        return redirect(url_for('escrow.my_escrows'))

    return render_template(
        "escrow/offer_form.html",
        product=product,
        form=form,
        last_completed_escrow=last_completed_escrow
    )


# routes/order.py (or wherever appropriate)
@escrow_bp.route("/create-order/<int:product_id>", methods=["GET", "POST"])
@login_required
def create_order(product_id):
    form = CreateOrderForm()
    product = Product.query.get_or_404(product_id)

    if form.validate_on_submit():
        quantity = form.quantity.data
        agreed_price = product.price
        total_amount = agreed_price * quantity

        order = Order(
            buyer_id=current_user.id,
            seller_id=product.user_id,
            product_id=product.id,
            quantity=quantity,
            agreed_price=form.agreed_price.data,
            total_amount=total_amount,
            status=StatusEnum.pending.value,  # inserts 'pending'
            payment_status=PaymentStatus.pending.value,  # inserts 'pending'
            order_status = OrderStatus.INITIATED.value,

        )

        db.session.add(order)
        db.session.commit()
        flash("Order created successfully!", "success")
        return redirect(url_for("seller_dashboard.my_orders"))

    return render_template("create_order.html", form=form, product=product)

# escrow_routes.py
@escrow_bp.route("/start", methods=["GET", "POST"])
@login_required
def start_escrow():
    if request.method == "POST":
        product_id = request.form.get("product_id")
        product = Product.query.get(product_id)
        if not product:
            flash("Invalid product", "danger")
            return redirect(url_for("escrow.start_escrow"))

        # make sure buyer is not the owner
        if product.user_id == current_user.id:
            flash("You cannot start escrow with your own product", "warning")
            return redirect(url_for("escrow.start_escrow"))

        # proceed with escrow creation...
        # ...

    # ✅ Instead of only showing current_user.products,
    # provide a searchable product list (or seller search)
    products = Product.query.filter(Product.is_deleted == False).all()

    return render_template("escrow/start.html", products=products)


# escrow_routes.py
@escrow_bp.route('/search-products', methods=['GET'])
def search_products():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    # Search by product title or seller name
    products = Product.query.join(User, Product.user_id == User.id).filter(
        (Product.title.ilike(f"%{query}%")) |
        (User.first_name.ilike(f"%{query}%")) |
        (User.last_name.ilike(f"%{query}%"))
    ).limit(10).all()

    results = [
        {
            "id": p.id,
            "title": p.title,
            "seller": f"{p.user.first_name} {p.user.last_name}"
        }
        for p in products
    ]
    return jsonify(results)

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
def money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@escrow_bp.route('/pay-via-wallet/<int:escrow_id>', methods=['POST'])
@login_required
def pay_via_wallet(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()

    # Base amount = seller's offer
    base_amount = Decimal(str(escrow.amount))  # seller offer

    # Admin fee = 3% of base
    admin_rate = Decimal("0.03")
    admin_fee = (base_amount * admin_rate).quantize(Decimal("0.01"))

    # Total deduction from buyer = base + admin fee
    total_amount = (base_amount + admin_fee).quantize(Decimal("0.01"))

    wallet_balance = Decimal(str(wallet.balance if wallet else "0.00"))
    if not wallet or wallet_balance < total_amount:
        flash(f"Insufficient wallet balance. Wallet: ₦{wallet_balance:.2f}", "danger")
        return redirect(url_for('escrow.my_escrows'))

    # Deduct full amount from buyer wallet
    wallet.balance = (wallet_balance - total_amount).quantize(Decimal("0.01"))

    # Lock escrow
    escrow.status = 'paid'
    escrow.is_paid = True
    escrow.paid_at = datetime.utcnow()

    # Persist amounts
    escrow.base_amount = base_amount
    escrow.admin_fee = admin_fee
    escrow.amount_to_seller = base_amount
    escrow.total_amount = total_amount

    db.session.commit()

    flash(
        f"Payment of ₦{total_amount:.2f} made via wallet. "
        f"Seller gets ₦{base_amount:.2f}, Admin fee: ₦{admin_fee:.2f}.",
        "success"
    )
    return redirect(url_for('escrow.my_escrows'))


@escrow_bp.route("/escrow/initiate", methods=["POST"])
@login_required
def initiate_escrow():
    data = request.json
    provider_id = data.get("provider_id")
    amount = float(data.get("amount"))

    success, result = create_pending_escrow(current_user.id, provider_id, amount)
    if not success:
        return jsonify({"status": "error", "message": result}), 400
    return jsonify({"status": "success", "escrow_id": result.id})

@escrow_bp.route("/escrow/release", methods=["POST"])
@login_required
def release_funds():
    data = request.json
    escrow_id = data.get("escrow_id")
    release_amount = float(data.get("amount", 0))

    success, message = release_escrow(escrow_id, release_amount, released_by=current_user.id)
    if not success:
        return jsonify({"status": "error", "message": message}), 400
    return jsonify({"status": "success", "message": message})


@escrow_bp.route("/notifications", methods=["GET"])
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    return jsonify([{"message": n.message, "read": n.read, "created_at": n.created_at} for n in notifs])


def create_pending_escrow(payer_id, provider_id, amount):
    wallet = Wallet.query.filter_by(user_id=payer_id).first()
    if not wallet or wallet.balance < amount:
        return False, "Insufficient balance"

    wallet.balance -= amount
    escrow = EscrowPayment(payer_id=payer_id, provider_id=provider_id, amount=amount)
    db.session.add(escrow)
    db.session.commit()

    log_action(escrow.id, "created", amount, payer_id)
    return True, escrow


def release_escrow(escrow: EscrowPayment):
    if escrow.status != "released":
        escrow.partial_release_amount = escrow.amount
        escrow.status = "released"
        # Update provider wallet
        provider_wallet = Wallet.query.filter_by(user_id=escrow.provider_id).first()
        provider_wallet.balance += escrow.amount
        db.session.commit()

        # Notify via Socket.IO
        socketio.emit(
            "escrow_update",
            {
                "escrow_id": escrow.id,
                "released_amount": escrow.partial_release_amount,
                "pending_amount": 0,
                "status": escrow.status
            },
            to=f"user_{escrow.payer_id}"
        )
        socketio.emit(
            "escrow_update",
            {
                "escrow_id": escrow.id,
                "released_amount": escrow.partial_release_amount,
                "pending_amount": 0,
                "status": escrow.status
            },
            to=f"user_{escrow.provider_id}"
        )



def log_action(escrow_id, action, amount, performed_by):
    audit = EscrowAudit(escrow_id=escrow_id, action=action, amount=amount, performed_by=performed_by)
    db.session.add(audit)
    db.session.commit()


def send_notification(user_id, message):
    # Save to DB
    notification = Notification(user_id=user_id, message=message)
    db.session.add(notification)
    db.session.commit()

    # Emit real-time notification
    socketio.emit(
        "new_notification",
        {"message": message},
        to=f"user_{user_id}"  # private room per user
    )



@escrow_bp.route("/escrow/release-all", methods=["POST"])
@login_required
def release_all_escrows():
    data = request.json
    escrow_ids = data.get("escrow_ids", [])
    if not escrow_ids:
        return jsonify({"status": "error", "message": "No escrows provided"}), 400

    for escrow_id in escrow_ids:
        # Release full remaining amount
        escrow = EscrowPayment.query.get(int(escrow_id))
        if escrow and escrow.status != "released":
            remaining = escrow.amount - (escrow.partial_release_amount or 0)
            release_escrow(escrow_id, release_amount=remaining, released_by=current_user.id)

    return jsonify({"status": "success", "message": "All pending escrows released"})


