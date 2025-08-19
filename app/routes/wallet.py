# app/routes/wallet.py

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Wallet

wallet_bp = Blueprint("wallet", __name__, url_prefix="/wallet")

@wallet_bp.route("/", methods=["GET"])
@login_required
def wallet_page():
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    if not wallet:
        flash("Wallet not found.", "danger")
        return redirect(url_for("seller_dashboard.my_dashboard"))  # or any fallback

    return render_template("wallet/history.html", wallet=wallet)

