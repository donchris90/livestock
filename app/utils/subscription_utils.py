# app/utils/subscription_utils.py or similar
from app.extensions import db
from app.models import EscrowPayment,AdminRevenue,User
import uuid
from datetime import datetime


def get_upload_limit(plan):
    plan = plan.lower() if plan else 'free'
    limits = {
        'free': 2,
        'starter': 5,
        'pro': 10,
        'premium': 100
    }
    return limits.get(plan, 2)

def handle_booking_payment(buyer_id, seller_id, product_id, full_amount):
    admin_fee = round(full_amount * 0.1, 2)
    base_amount = full_amount - admin_fee

    buyer = User.query.get(buyer_id)
    seller = User.query.get(seller_id)

    reference = f"ESCROW_{uuid.uuid4().hex[:10].upper()}"

    payment = EscrowPayment(
        buyer_id=buyer_id,
        seller_id=seller_id,
        product_id=product_id,
        reference=reference,
        total_amount=full_amount,
        base_amount=base_amount,
        escrow_fee=admin_fee,
        admin_fee=admin_fee,
        amount_to_seller=base_amount,
        is_paid=True,
        paid_at=datetime.utcnow(),
        status="paid",
        is_released=False,
        is_withdrawn=False,
        buyer_name=buyer.full_name if buyer else "",
        seller_name=seller.full_name if seller else ""
    )
    db.session.add(payment)

    # Log admin revenue
    revenue = AdminRevenue(
        amount=admin_fee,
        source="escrow",
        reference=reference
    )
    db.session.add(revenue)

    db.session.commit()
    return payment

