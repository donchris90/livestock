from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app.models import Product, db,WalletTransaction,PromotionPayment,PromotionHistory
from app.forms import PromoteProductForm,PromotionForm
from app.utils.promotion import get_price_for_promo
import requests
import  uuid
import os

promotion_bp = Blueprint('promotion', __name__)


@promotion_bp.route("/featured")
@login_required
def featured_products():
    # List user’s products for promotion
    return render_template("promotion/feature.html")

@promotion_bp.route("/boost")
@login_required
def boost_products():
    return render_template("boost.html")

@promotion_bp.route("/top")
@login_required
def top_products():
    return render_template("promotion/top.html")


PROMOTION_PRICING = {
    "featured": {7: 100, 30: 1500, 60: 2500},
    "boosted": {7: 100, 30: 2500, 60: 4000},
    "top": {7: 100, 30: 3000, 60: 5000}
}



@promotion_bp.route("/promote/<int:product_id>", methods=["GET", "POST"])
@login_required
def promote_product(product_id):
    product = Product.query.get_or_404(product_id)
    form = PromotionForm()

    if form.validate_on_submit():
        promo_type = form.promo_type.data
        days = int(form.days.data)
        price = PROMOTION_PRICING[promo_type][days]

        reference = f"{product.id}-{uuid.uuid4().hex[:10]}"
        payment = PromotionPayment(
            product_id=product.id,
            promo_type=promo_type,
            days=days,
            price=price,
            reference=reference
        )
        db.session.add(payment)
        db.session.commit()

        # Redirect to Paystack
        callback_url = url_for('promotion.verify_payment', _external=True)
        paystack_url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}"
        }
        payload = {
            "email": current_user.email,
            "amount": price * 100,  # kobo
            "reference": reference,
            "callback_url": callback_url
        }

        response = requests.post(paystack_url, headers=headers, json=payload).json()

        if response.get("status"):
            return redirect(response["data"]["authorization_url"])
        else:
            flash("Payment initialization failed.", "danger")
            return redirect(url_for("seller_dashboard.my_dashboard"))

    return render_template("promotion/promote_product.html", product=product, form=form, pricing=PROMOTION_PRICING)

@promotion_bp.route("/paystack/callback")
def paystack_callback():
    reference = request.args.get("reference")

    # Verify the transaction
    headers = {
        "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}"
    }
    response = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    res_data = response.json()

    if res_data.get("status") and res_data["data"]["status"] == "success":
        # Mark as paid
        payment = PromotionPayment.query.filter_by(reference=reference).first()
        if payment:
            payment.status = "paid"
            payment.paid_at = datetime.utcnow()
            db.session.commit()

            # Promote the product (you can customize this logic)
            product = Product.query.get(payment.product_id)
            product.is_promoted = True
            product.promotion_type = payment.promo_type
            product.promotion_expiry = datetime.utcnow() + timedelta(days=int(payment.days))
            db.session.commit()

            flash("Payment successful! Your product is now promoted.", "success")
        return redirect(url_for("seller_dashboard.my_dashboard"))
    else:
        flash("Payment failed or not verified.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))


@promotion_bp.route("/verify-payment")
@login_required
def verify_payment():
    reference = request.args.get("reference")
    if not reference:
        flash("No payment reference found.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # ✅ Verify payment with Paystack
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}"
    }
    try:
        response = requests.get(verify_url, headers=headers).json()
    except Exception as e:
        flash("Failed to connect to Paystack.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))

    # ✅ Check if payment was successful
    if response.get("data", {}).get("status") == "success":
        payment = PromotionPayment.query.filter_by(reference=reference).first()

        if not payment:
            flash("Payment record not found.", "danger")
            return redirect(url_for("seller_dashboard.my_dashboard"))

        if payment.status == "paid":
            flash("Payment has already been verified.", "info")
            return redirect(url_for("seller_dashboard.my_dashboard"))

        # ✅ Mark payment as paid
        payment.status = "paid"
        payment.paid_at = datetime.utcnow()

        # ✅ Fetch the product
        product = Product.query.get(payment.product_id)
        if not product:
            flash("Product not found.", "danger")
            return redirect(url_for("seller_dashboard.my_dashboard"))

        # ✅ Apply promotion based on type
        days = payment.days or 7  # Default to 7 days
        product.promotion_type = payment.promo_type
        product.updated_at = datetime.utcnow()

        if payment.promo_type == "featured":
            product.is_featured = True
            product.featured_expiry = datetime.utcnow() + timedelta(days=days)

        elif payment.promo_type == "boosted":
            product.is_boosted = True
            product.boost_expiry = datetime.utcnow() + timedelta(days=days)

        elif payment.promo_type == "top":
            product.is_top = True
            product.top_expiry = datetime.utcnow() + timedelta(days=days)

        db.session.commit()
        # After db.session.commit() on product
        history = PromotionHistory(
            product_id=product.id,
            user_id=product.user_id,
            promo_type=payment.promo_type,
            reference=payment.reference,
            started_at=datetime.utcnow(),
            ends_at=datetime.utcnow() + timedelta(days=days)
        )
        db.session.add(history)
        db.session.commit()

        # After db.session.commit() on product
        history = PromotionHistory(
            product_id=product.id,
            user_id=product.user_id,
            promo_type=payment.promo_type,
            reference=payment.reference,
            started_at=datetime.utcnow(),
            ends_at=datetime.utcnow() + timedelta(days=days)
        )
        db.session.add(history)
        db.session.commit()

        # ✅ Credit admin wallet
        from app.models import Wallet, User

        admin = User.query.filter_by(role="admin").first()
        admin_wallet = Wallet.query.filter_by(user_id=admin.id).first()

        if admin_wallet:
            boost_amount = payment.price
            admin_wallet.balance += boost_amount
            admin_wallet.promotion_revenue += boost_amount
            db.session.commit()
        else:
            print("Admin wallet not found.")

        flash(f"Your product has been promoted as {payment.promo_type.title()}!", "success")
    else:
        flash("Payment verification failed or was not successful.", "danger")

    return redirect(url_for("seller_dashboard.my_dashboard"))


@promotion_bp.route("/promotion-success/<reference>")
@login_required
def promotion_success(reference):
    payment = PromotionPayment.query.filter_by(reference=reference, status="pending").first()
    if not payment:
        flash("Invalid or already processed payment.", "danger")
        return redirect(url_for("main.home"))

    product = Product.query.get(payment.product_id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("main.home"))

    # Mark as promoted
    product.is_promoted = True
    product.promotion_type = payment.promo_type
    product.promotion_end_date = datetime.utcnow() + timedelta(days=payment.days)

    payment.status = "paid"
    payment.paid_at = datetime.utcnow()

    db.session.commit()

    flash("Product successfully promoted!", "success")
    return redirect(url_for("main.home"))