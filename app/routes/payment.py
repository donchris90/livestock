from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, Product, User

payment_bp = Blueprint('payment', __name__)

# Simulated escrow purchase
@payment_bp.route('/purchase/<int:product_id>', methods=['POST'])
@jwt_required()
def purchase_product(product_id):
    current_user = get_jwt_identity()
    buyer_id = current_user['user_id']

    product = Product.query.get(product_id)
    if not product:
        return jsonify({"message": "Product not found."}), 404

    if product.owner_id == buyer_id:
        return jsonify({"message": "You cannot purchase your own product."}), 400

    # Simulated payment flow (you can later replace this with Stripe/Paystack integration)
    sale_price = product.price
    commission_rate = 0.05
    commission_amount = round(sale_price * commission_rate, 2)
    seller_amount = round(sale_price - commission_amount, 2)

    # Simulate storing escrow
    escrow = {
        "buyer_id": buyer_id,
        "seller_id": product.owner_id,
        "product_id": product.id,
        "amount_paid": sale_price,
        "commission": commission_amount,
        "seller_gets": seller_amount,
        "status": "held_in_escrow"
    }

    return jsonify({
        "message": f"Payment of NGN {sale_price} received and held in escrow.",
        "escrow": escrow
    }), 200

# Simulated delivery confirmation
@payment_bp.route('/confirm-delivery/<int:product_id>', methods=['POST'])
@jwt_required()
def confirm_delivery(product_id):
    current_user = get_jwt_identity()
    buyer_id = current_user['user_id']

    product = Product.query.get(product_id)
    if not product:
        return jsonify({"message": "Product not found."}), 404

    if product.owner_id == buyer_id:
        return jsonify({"message": "Sellers cannot confirm their own delivery."}), 400

    # Mark payment as released (in a real app, update DB/payment gateway)
    return jsonify({
        "message": f"Delivery confirmed. Funds released to seller (User ID: {product.owner_id})."
    }), 200
