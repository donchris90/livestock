from flask import Blueprint, redirect, url_for, flash, render_template, request, current_app
from flask_login import login_required, current_user
from app.utils.paystack import initiate_paystack_transfer,verify_paystack_payment
from app.extensions import db
from app.forms import WithdrawalFormSelect, UsePayoutAccountForm,AdminWithdrawalForm
from app.models import BankDetails, WalletTransaction,Wallet,PayoutTransaction, Product
from datetime import datetime, timedelta
from sqlalchemy import func
import os

import requests

payout_bp = Blueprint("payout", __name__)

@payout_bp.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw_funds():
    form = WithdrawalFormSelect()
    user = current_user

    # 🧠 Pull same balance logic as dashboard
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    balance = wallet.balance if wallet else 0.0

    if request.method == "POST" and form.validate_on_submit():
        amount = float(form.amount.data)

        if amount > balance:
            flash("Withdrawal failed: Insufficient wallet balance.", "danger")
        else:
            amount_in_kobo = int(amount * 100)
            payout_account = BankDetails.query.filter_by(user_id=user.id).first()

            if payout_account:
                response = initiate_paystack_transfer(
                    amount_in_kobo,
                    payout_account.recipient_code,
                    reason="Wallet withdrawal"
                )

                if response.get("status"):
                    wallet.balance -= amount
                    db.session.add(PayoutTransaction(
                        user_id=user.id,
                        amount=amount,
                        status="success",
                        reference=response["data"]["reference"]
                    ))
                    db.session.commit()
                    flash("Withdrawal successful!", "success")
                    return redirect(url_for("payout.withdraw_funds"))
                else:
                    flash(f"Withdrawal failed: {response.get('message')}", "danger")
            else:
                flash("No payout account found. Please set up your bank details.", "warning")

    return render_template("wallet/withdraw.html", form=form, balance=balance)

@payout_bp.route("/use-payout-account", methods=["GET", "POST"])
@login_required
def use_payout_account():
    form = UsePayoutAccountForm()
    accounts = BankDetails.query.filter_by(user_id=current_user.id).all()

    form.payout_account.choices = [
        (str(acc.id), f"{acc.bank_name} - {acc.account_number} ({acc.account_name})")
        for acc in accounts
    ]

    if request.method == "POST":
        if form.validate_on_submit():
            selected_id = form.payout_account.data
            current_user.selected_payout_account_id = selected_id
            db.session.commit()

            flash("Payout account selected", "success")
            return redirect(url_for("seller_dashboard.my_dashboard"))
        else:
            flash("Please select a valid account", "danger")

    return render_template("wallet/use_payout_account.html", form=form)


# Promotions
@payout_bp.route("/promotion-success")
@login_required
def promotion_success():
    reference = request.args.get("reference")
    product_id = request.args.get("product_id")
    promo_type = request.args.get("promo_type")

    product = Product.query.get_or_404(product_id)

    if verify_paystack_payment(reference):
        now = datetime.utcnow()
        if promo_type == 'featured':
            product.is_featured = True
            product.featured_expiry = now + timedelta(days=7)
        elif promo_type == 'boost':
            product.is_boosted = True
            product.boost_expiry = now + timedelta(days=7)
        elif promo_type == 'top':
            product.is_top = True
            product.top_expiry = now + timedelta(days=7)

        db.session.commit()
        flash(f"{promo_type.title()} promotion activated!", "success")
    else:
        flash("Payment verification failed.", "danger")

    return redirect(url_for("seller_dashboard.my_dashboard"))

@payout_bp.route("/admin-withdraw", methods=["GET", "POST"])
@login_required  # Only if you're using admin login
def admin_withdraw():
    form = AdminWithdrawalForm()
    admin_wallet_balance = db.session.query(
        func.coalesce(func.sum(WalletTransaction.amount), 0)
    ).filter(WalletTransaction.transaction_type == 'credit').scalar()

    if form.validate_on_submit():
        amount = form.amount.data

        if amount > admin_wallet_balance:
            flash("Insufficient balance", "danger")
            return redirect(url_for("payout.admin_withdraw"))

        # Step 1: Create Paystack recipient
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}"
        }
        payload = {
            "type": "nuban",
            "name": form.account_name.data,
            "account_number": form.account_number.data,
            "bank_code": form.bank_code.data,
            "currency": "NGN"
        }
        res = requests.post("https://api.paystack.co/transferrecipient", json=payload, headers=headers)
        data = res.json()

        if not data.get("status"):
            flash("Paystack error: " + data.get("message", "Unknown error"), "danger")
            return redirect(url_for("payout.admin_withdraw"))

        recipient_code = data["data"]["recipient_code"]

        # Step 2: Initiate Transfer
        transfer_payload = {
            "source": "balance",
            "amount": int(amount * 100),  # kobo
            "recipient": recipient_code,
            "reason": "Admin Withdrawal"
        }
        trans_res = requests.post("https://api.paystack.co/transfer", json=transfer_payload, headers=headers)
        trans_data = trans_res.json()

        if not trans_data.get("status"):
            flash("Transfer failed: " + trans_data.get("message", "Unknown error"), "danger")
            return redirect(url_for("payout.admin_withdraw"))

        # Step 3: Record transaction
        new_tx = WalletTransaction(
            user_id=current_user.id,
            amount=amount,
            transaction_type="debit",
            description="Admin withdrawal to " + form.account_number.data,
            status="completed"
        )
        db.session.add(new_tx)
        db.session.commit()

        flash("Withdrawal successful!", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/withdraw.html", form=form, admin_wallet_balance=admin_wallet_balance)
