import requests
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app,abort
from flask_login import current_user, login_required
from app.forms import EscrowPaymentForm
from app.models import Product, EscrowPayment
from app.extensions import db
from datetime import datetime, timedelta, time
import time

escrow_bp = Blueprint('escrow', __name__, url_prefix='/escrow')


@escrow_bp.route('/preview-escrow/<int:product_id>', methods=['POST'])
@login_required
def preview_escrow(product_id):
    amount = float(request.form['amount'])
    product = Product.query.get_or_404(product_id)
    fee = round(amount * 0.02, 2)
    total = round(amount + fee, 2)

    new_escrow = EscrowPayment(
        buyer_id=current_user.id,
        seller_id=product.user_id,
        product_id=product.id,
        base_amount=amount,
        escrow_fee=fee,
        total_amount=total
    )
    db.session.add(new_escrow)
    db.session.commit()

    flash("Escrow request saved. Proceed to payment.")
    return redirect(url_for('escrow.pay_escrow', escrow_id=new_escrow.id))


@escrow_bp.route('/pay-escrow/<int:escrow_id>')
@login_required
def pay_escrow(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    # Generate paystack payload
    paystack_data = {
        "email": current_user.email,
        "amount": int(escrow.total_amount * 100),  # in kobo
        "reference": f"escrow_{escrow.id}_{int(time.time())}",
        "callback_url": url_for('escrow.verify_payment', escrow_id=escrow.id, _external=True)
    }

    # Save ref
    escrow.paystack_ref = paystack_data["reference"]
    db.session.commit()

    # Redirect to paystack (front-end preferred, here we simulate server-side)
    return redirect(
        f"https://paystack.com/pay/YOUR_SLUG?amount={paystack_data['amount']}&email={paystack_data['email']}&reference={paystack_data['reference']}")


@escrow_bp.route('/verify-payment/<int:escrow_id>')
@login_required
def verify_payment(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)

    # Simulated Paystack response (in real app, make HTTP request to Paystack API)
    # Assume success for now
    escrow.status = 'paid'
    db.session.commit()

    flash("Payment successful. Funds in escrow.")
    return redirect(url_for('buyer.dashboard'))


@escrow_bp.route('/confirm-order/<int:escrow_id>', methods=['POST'])
@login_required
def confirm_order(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)
    if escrow.buyer_id != current_user.id or escrow.status != 'paid':
        abort(403)

    escrow.status = 'released'
    db.session.commit()
    flash("Order confirmed. Funds released.")
    return redirect(url_for('buyer.dashboard'))


@escrow_bp.route('/confirm/<int:escrow_id>', methods=['GET'])
@login_required
def confirm_escrow(escrow_id):
    escrow = EscrowPayment.query.get_or_404(escrow_id)
    if escrow.buyer_id != current_user.id:
        abort(403)
    return render_template('escrow/confirm_escrow.html', escrow=escrow)



@escrow_bp.route('/initiate/<int:product_id>', methods=['GET'])
@login_required
def initiate_escrow(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('escrow/initiate_escrow.html', product=product)
