from flask import Blueprint, request, jsonify,current_app, render_template
from datetime import datetime
from app.models import db, ServiceEscrow, Wallet,WalletTransaction
from sqlalchemy.exc import SQLAlchemyError
from flask import request, jsonify
from flask_login import login_required, current_user
import requests, os


service_escrow_bp = Blueprint('service_escrow_bp', __name__)
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")  # load from .env
def get_or_create_wallet(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if wallet:
        return wallet
    wallet = Wallet(user_id=user_id, balance=0.0)
    db.session.add(wallet)
    db.session.commit()
    return wallet

@service_escrow_bp.route('/create-service-escrow', methods=['POST'])
def create_service_escrow():
    data = request.get_json()
    buyer_id = data.get('buyer_id')
    provider_id = data.get('provider_id')
    booking_id = data.get('booking_id')
    role = data.get('role')  # 'agent' or 'logistics'
    amount = data.get('amount')

    try:
        buyer_wallet = get_or_create_wallet(buyer_id)

        if buyer_wallet.balance < amount:
            return jsonify({'error': 'Insufficient balance'}), 400

        buyer_wallet.balance -= amount

        escrow = ServiceEscrow(
            buyer_id=buyer_id,
            provider_id=provider_id,
            booking_id=booking_id,
            role=role,
            amount=amount,
            is_released=False
        )

        db.session.add(escrow)
        db.session.commit()
        return jsonify({'message': 'Escrow created successfully'}), 201

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@service_escrow_bp.route('/release-service-escrow/<int:escrow_id>', methods=['POST'])
def release_service_escrow(escrow_id):
    try:
        escrow = ServiceEscrow.query.get_or_404(escrow_id)

        if escrow.is_released:
            return jsonify({'error': 'Escrow already released'}), 400

        amount = escrow.amount
        admin_share = round(amount * 0.02, 2)
        provider_share = round(amount * 0.98, 2)

        provider_wallet = get_or_create_wallet(escrow.provider_id)
        admin_wallet = get_or_create_wallet(1)  # assuming user_id=1 is admin

        provider_wallet.balance += provider_share
        admin_wallet.balance += admin_share

        escrow.is_released = True
        escrow.released_at = datetime.utcnow()

        db.session.commit()
        return jsonify({'message': 'Escrow released successfully'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@service_escrow_bp.route('/topup-wallet', methods=['POST'])
def topup_wallet():
    data = request.get_json()
    user_id = data.get('user_id')
    amount = data.get('amount')
    reference = data.get('reference')

    try:
        # Optional: You can verify Paystack payment via their API here using the reference

        wallet = get_or_create_wallet(user_id)
        wallet.balance += float(amount)
        db.session.commit()

        return jsonify({'message': 'Wallet successfully topped up'}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@service_escrow_bp.route('/create-topup-session', methods=['POST'])
@login_required
def create_topup_session():
    data = request.get_json()
    amount = data.get('amount')

    if not amount or float(amount) <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    paystack_data = {
        "email": current_user.email,
        "amount": int(float(amount) * 100),  # Convert to kobo
        "metadata": {
            "user_id": current_user.id,
            "purpose": "wallet_topup"
        }
    }

    response = requests.post("https://api.paystack.co/transaction/initialize", json=paystack_data, headers=headers)
    res_data = response.json()

    if response.status_code != 200 or not res_data.get("status"):
        return jsonify({'error': 'Failed to initialize payment'}), 500

    auth_url = res_data["data"]["authorization_url"]
    return jsonify({"payment_url": auth_url})

from decimal import Decimal, ROUND_HALF_UP

@service_escrow_bp.route('/verify-topup/<reference>', methods=['GET'])
def verify_topup(reference):
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers,
            timeout=10
        )
        result = response.json()
        print("🔍 PAYSTACK VERIFY RESPONSE:", result)  # debug log
    except Exception as e:
        return jsonify({"error": f"Failed to contact Paystack: {str(e)}"}), 500

    # --- Validate API response ---
    if not result.get("status"):
        return jsonify({"error": f"Verification failed: {result.get('message', 'Unknown error')}"}), 400

    data = result.get("data", {})
    if data.get("status") != "success":
        return jsonify({"error": f"Payment not successful. Status: {data.get('status')}"}), 400

    # --- Metadata & Amount ---
    metadata = data.get("metadata", {}) or {}
    user_id = metadata.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id in Paystack metadata"}), 400

    try:
        amount = Decimal(data.get("amount", 0)) / Decimal(100)  # convert to Naira
    except Exception as e:
        return jsonify({"error": f"Invalid amount format: {str(e)}"}), 400

    try:
        # --- Fee and Net ---
        fee = (amount * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_amount = (amount - fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # --- Wallets ---
        user_wallet = get_or_create_wallet(user_id)
        admin_wallet = get_or_create_wallet(7)  # admin user_id

        # --- Update balances (cast to Decimal if your model uses it) ---
        user_wallet.balance = (Decimal(user_wallet.balance) + net_amount).quantize(Decimal("0.01"))
        admin_wallet.balance = (Decimal(admin_wallet.balance) + fee).quantize(Decimal("0.01"))

        # --- Transactions ---
        user_transaction = WalletTransaction(
            user_id=user_id,
            wallet_id=user_wallet.id,
            amount=net_amount,
            transaction_type="topup",
            description=f"Wallet top-up of ₦{net_amount} (₦{fee} fee deducted)",
            status="success",
            reference=reference
        )
        admin_transaction = WalletTransaction(
            user_id=7,
            wallet_id=admin_wallet.id,
            amount=fee,
            transaction_type="fee_income",
            description=f"1% top-up fee from user {user_id}",
            status="success",
            reference=reference
        )

        db.session.add(user_transaction)
        db.session.add(admin_transaction)
        db.session.commit()

        return jsonify({
            "message": f"✅ Wallet credited with ₦{net_amount}, ₦{fee} sent to admin as fee",
            "wallet_balance": float(user_wallet.balance)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update wallet: {str(e)}"}), 500
