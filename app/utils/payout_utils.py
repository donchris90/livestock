import os
import requests
from dotenv import load_dotenv
from app.models import User,Wallet
from app import create_app, db
from decimal import Decimal

load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")

headers = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type": "application/json"
}


def initiate_paystack_transfer(bank_code, account_number, amount, name):
    """
    Initiates a real payout via Paystack.
    :param bank_code: e.g., '058' (GTB)
    :param account_number: e.g., '0123456789'
    :param amount: in kobo (e.g., ₦1000 = 100000)
    :param name: Full name of recipient
    :return: dict with status and message/data
    """
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    # 1. Create transfer recipient
    recipient_url = "https://api.paystack.co/transferrecipient"
    recipient_data = {
        "type": "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN"
    }

    try:
        r = requests.post(recipient_url, json=recipient_data, headers=headers)
        res = r.json()
        if not res.get("status"):
            return {"status": False, "message": res.get("message", "Could not create recipient")}
        recipient_code = res["data"]["recipient_code"]
    except Exception as e:
        return {"status": False, "message": f"Recipient creation error: {str(e)}"}

    # 2. Make transfer
    transfer_url = "https://api.paystack.co/transfer"
    transfer_data = {
        "source": "balance",
        "amount": amount,
        "recipient": recipient_code,
        "reason": f"Payout to {name}"
    }

    try:
        r = requests.post(transfer_url, json=transfer_data, headers=headers)
        res = r.json()
        if res.get("status"):
            return {"status": True, "data": res["data"]}
        else:
            return {"status": False, "message": res.get("message", "Transfer failed")}
    except Exception as e:
        return {"status": False, "message": f"Transfer error: {str(e)}"}


def get_or_create_wallet(user_id=None, is_admin=False):
    if is_admin:
        wallet = Wallet.query.filter_by(user_id=None).first()  # dedicated admin wallet has no user_id
        if not wallet:
            wallet = Wallet(user_id=None, balance=0.0)
            db.session.add(wallet)
            db.session.commit()
        return wallet

    # Normal user wallet
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()
    return wallet


from decimal import Decimal, ROUND_DOWN
def to_decimal(value):
    """Convert value to Decimal safely."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

def get_admin_wallet():
    wallet = Wallet.query.filter_by(is_admin=True).first()
    if not wallet:
        wallet = Wallet(balance=0, is_admin=True)
        db.session.add(wallet)
        db.session.commit()
    return wallet
