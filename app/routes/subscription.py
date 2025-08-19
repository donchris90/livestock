# routes/subscription.py

from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import SubscriptionPlan, db,ProfitHistory, PlatformWallet,Subscription
import requests, os
from flask_login import login_user

subscription_bp = Blueprint("subscription", __name__, url_prefix="/subscription")

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")


@subscription_bp.route("/upgrade", methods=["GET"])
@login_required
def upgrade():
    plans = SubscriptionPlan.query.all()
    return render_template("subscription/upgrade.html", plans=plans, current_plan=current_user.subscription_plan)


@subscription_bp.route('/create-payment', methods=['GET', 'POST'])
@login_required
def create_payment():
    plan_id = request.form.get("plan_id")
    plan = SubscriptionPlan.query.get_or_404(plan_id)

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "email": current_user.email,
        "amount": int(plan.price * 100),  # amount in kobo
        "metadata": {
            "plan": plan.name,
            "user_id": current_user.id,
            "redirect_url": url_for("subscription.verify_payment", _external=True)
        },
        "callback_url": url_for("subscription.verify_payment", _external=True)
    }

    response = requests.post("https://api.paystack.co/transaction/initialize", json=data, headers=headers)

    if response.status_code == 200:
        auth_url = response.json()["data"]["authorization_url"]
        return redirect(auth_url)
    else:
        flash("❌ Failed to initialize payment. Please try again.", "danger")
        return redirect(url_for("subscription.upgrade"))


@subscription_bp.route("/verify-payment")
@login_required
def verify_payment():
    reference = request.args.get("reference")
    if not reference:
        flash("Invalid payment reference.", "danger")
        return redirect(url_for("subscription.upgrade"))

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }

    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    response = requests.get(verify_url, headers=headers)

    if response.status_code == 200:
        data = response.json().get("data")
        if data and data.get("status") == "success":
            amount = data.get("amount", 0) / 100  # convert from kobo to naira
            metadata = data.get("metadata", {})
            plan_name = metadata.get("plan")

            plan = SubscriptionPlan.query.filter_by(name=plan_name).first()
            if plan:
                current_user.subscription_plan = plan.name
                current_user.plan_name = plan.name
                current_user.upload_limit = plan.upload_limit

                if plan.duration_days:
                    expiry = datetime.utcnow() + timedelta(days=plan.duration_days)
                    current_user.subscription_expiry = expiry
                    current_user.grace_end = expiry + timedelta(days=3)
                else:
                    current_user.subscription_expiry = None
                    current_user.grace_end = None

                # ✅ Save subscription payment
                subscription_payment = Subscription(
                    user_id=current_user.id,
                    amount=amount,
                    reference=reference,
                    plan_name=plan.name,
                    status="success",
                    created_at=datetime.utcnow()
                )
                db.session.add(subscription_payment)

                # ✅ Log profit history
                log = ProfitHistory(
                    user_id=current_user.id,
                    source_type='subscription',
                    description=f"{plan_name} Subscription",
                    amount=amount,
                    reference=reference,
                    status="success"
                )
                db.session.add(log)

                # ✅ Update platform wallet
                wallet = PlatformWallet.query.get(1) or PlatformWallet(id=1)
                wallet.balance = (wallet.balance or 0) + amount
                wallet.total_earned = (wallet.total_earned or 0.0) + amount
                db.session.add(wallet)

                db.session.commit()
                login_user(current_user, fresh=True)
                flash(f"✅ Subscription to {plan.name} plan successful!", "success")
            else:
                flash("❗ Payment succeeded, but plan not found in the database.", "warning")
        else:
            flash("❌ Payment was not successful.", "danger")
    else:
        flash("❌ Could not verify payment at the moment.", "danger")

    return redirect(url_for("main.home"))


@subscription_bp.route("/simulate-plan/<plan_name>")
@login_required
def simulate_plan(plan_name):
    from app.utils.subscription_utils import get_upload_limit

    plan = plan_name.lower()
    allowed_plans = ['free', 'starter', 'pro', 'premium']
    if plan not in allowed_plans:
        flash("Invalid plan name.", "danger")
        return redirect(url_for("subscription.upgrade"))

    current_user.plan_name = plan
    current_user.upload_limit = get_upload_limit(plan)

    # Simulate subscription expiry and grace (optional)
    current_user.subscription_expiry = datetime.utcnow() + timedelta(days=30)
    current_user.grace_end = current_user.subscription_expiry + timedelta(days=3)

    db.session.commit()
    login_user(current_user, fresh=True)
    flash(f"✅ Plan simulated: {plan.capitalize()}", "success")
    return redirect(url_for("main.home"))
