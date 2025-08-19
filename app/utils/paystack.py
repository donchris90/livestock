import os
import requests
from dotenv import load_dotenv
from app.models import EscrowPayment
from app import create_app, db
from app.models import User, Wallet  # or your correct import paths
from app import db


load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")

headers = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type": "application/json"
}

def initialize_transaction(email, amount, reference, callback_url):
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json"
    }
    data = {
        "email": email,
        "amount": int(amount * 100),  # Paystack expects amount in kobo
        "reference": reference,
        "callback_url": callback_url,
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Payment init error:", e)
        return None


def verify_paystack_payment(reference):
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print("Error verifying Paystack payment:", e)
        return None

import requests

def get_banks_from_paystack():
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    res = requests.get("https://api.paystack.co/bank", headers=headers)
    return res.json().get("data", [])

def verify_account_number(account_number, bank_code):
    url = f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    res = requests.get(url, headers=headers)
    data = res.json()
    if data.get("status") and data.get("data"):
        return data["data"]
    return None

def create_transfer_recipient(name, account_number, bank_code):
    url = "https://api.paystack.co/transferrecipient"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    payload = {
        "type": "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN"
    }
    res = requests.post(url, json=payload, headers=headers)
    data = res.json()
    if data.get("status"):
        return data["data"]
    return None



def transfer_funds_to_seller(escrow):
    try:
        # You should store seller's recipient_code when they set up payout
        seller = escrow.seller
        amount_kobo = int(escrow.amount * 100)

        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "source": "balance",
            "reason": f"Payout for product: {escrow.product.title}",
            "amount": amount_kobo,
            "recipient": seller.paystack_recipient_code  # stored when payout setup
        }

        response = requests.post("https://api.paystack.co/transfer", json=data, headers=headers)
        res_json = response.json()

        return res_json.get("status") is True

    except Exception as e:
        print("Transfer error:", e)
        return False

def create_recipient_code(account_number, bank_code):
    url = "https://api.paystack.co/transferrecipient"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "type": "nuban",
        "name": "Seller Payout",  # You can update with actual seller name
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN"
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result.get("status"):
        return result["data"]["recipient_code"]
    else:
        raise Exception(f"Error creating recipient code: {result.get('message')}")


def resolve_account_name(account_number, bank_code):
    url = f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result.get("status"):
        return result["data"]["account_name"]
    else:
        raise Exception(f"Could not resolve account name: {result.get('message')}")

import requests

def get_banks_from_api():
    url = "https://api.paystack.co/bank"
    headers = {
        "Authorization": f"Bearer PAYSTACK_SECRET_KEY"  # replace with your actual Paystack secret key
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("data", [])
    return []

def verify_account(account_number, bank_code):
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }
    url = f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}"

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code == 200 and data.get("status"):
        return data["data"]["account_name"]
    else:
        raise Exception(data.get("message", "Unable to verify account"))


def fetch_banks():
    headers = {
        "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}"
    }
    url = "https://api.paystack.co/bank"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Will raise HTTPError for 4xx/5xx
        data = response.json()

        if data.get("status"):
            return data["data"]
        else:
            print("Paystack error:", data)
            return []
    except requests.exceptions.RequestException as e:
        print("❌ Network or request error:", e)
        return []



import requests



def create_and_transfer_to_recipient(name, account_number, bank_code, amount, reason="Escrow payout"):
    # Step 1: Create Transfer Recipient
    recipient_url = "https://api.paystack.co/transferrecipient"
    recipient_headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    recipient_data = {
        "type": "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "NGN"
    }

    recipient_res = requests.post(recipient_url, json=recipient_data, headers=recipient_headers)
    if recipient_res.status_code != 200 or not recipient_res.json().get("status"):
        raise Exception("Failed to create transfer recipient")

    recipient_code = recipient_res.json()["data"]["recipient_code"]

    # Step 2: Initiate Transfer
    transfer_url = "https://api.paystack.co/transfer"
    transfer_data = {
        "source": "balance",
        "amount": int(amount * 100),  # Convert to kobo
        "recipient": recipient_code,
        "reason": reason
    }

    transfer_res = requests.post(transfer_url, json=transfer_data, headers=recipient_headers)
    if transfer_res.status_code != 200 or not transfer_res.json().get("status"):
        raise Exception("Failed to initiate transfer")

    return transfer_res.json()


def send_money_to_seller(recipient_code, amount, reason="Escrow Payout"):
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "source": "balance",
        "amount": int(amount * 100),  # Convert Naira to Kobo
        "recipient": recipient_code,
        "reason": reason
    }

    response = requests.post("https://api.paystack.co/transfer", json=data, headers=headers)
    return response.json()

def get_escrow_role_field(user_id):
    if EscrowPayment.query.filter_by(buyer_id=user_id).first():
        return EscrowPayment.buyer_id
    elif EscrowPayment.query.filter_by(seller_id=user_id).first():
        return EscrowPayment.seller_id
    elif EscrowPayment.query.filter_by(agent_id=user_id).first():
        return EscrowPayment.agent_id
    elif EscrowPayment.query.filter_by(vet_id=user_id).first():
        return EscrowPayment.vet_id
    elif EscrowPayment.query.filter_by(logistics_id=user_id).first():
        return EscrowPayment.logistics_id
    return None


import requests
import os

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")  # Or hardcode for local testing


def initiate_paystack_transfer(amount_in_kobo, recipient_code, reason=""):
    url = "https://api.paystack.co/transfer"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "source": "balance",
        "amount": amount_in_kobo,  # Amount in kobo
        "recipient": recipient_code,
        "reason": reason,
    }

    response = requests.post(url, json=data, headers=headers)
    return response.json()


def initiate_payout_to_seller(seller_id):
    # ✅ Fetch seller and wallet
    seller = User.query.get(seller_id)
    wallet = Wallet.query.filter_by(user_id=seller_id).first()

    # ✅ Basic checks
    if not seller:
        return {"status": False, "message": "Seller not found."}

    if not wallet or wallet.balance <= 0:
        return {"status": False, "message": "No funds to withdraw."}

    if not seller.bank_account_number or not seller.bank_code:
        return {"status": False, "message": "Bank details not set up."}

    # ✅ Prepare transfer
    amount_kobo = int(wallet.balance * 100)
    transfer_data = {
        "source": "balance",
        "amount": amount_kobo,
        "recipient": seller.recipient_code,  # ensure this exists
        "reason": "Payout to seller"
    }

    response = initiate_paystack_transfer(transfer_data)

    if response["status"]:
        wallet.balance = 0.00
        db.session.commit()
        return {"status": True, "message": f"₦{wallet.balance:,.2f} paid out."}
    else:
        return {"status": False, "message": response.get("message", "Paystack payout failed.")}


def initiate_paystack_transfer_to_recipient(recipient_code, amount, reason="Payout"):
    url = "https://api.paystack.co/transfer"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "source": "balance",
        "amount": amount,
        "recipient": recipient_code,
        "reason": reason
    }

    response = requests.post(url, json=data, headers=headers)
    return response.json()

#Promotions
def initiate_paystack_payment(amount, email, reference, callback_url):
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "amount": amount,
        "email": email,
        "reference": reference,
        "callback_url": callback_url
    }

    response = requests.post("https://api.paystack.co/transaction/initialize", json=data, headers=headers)
    return response.json()