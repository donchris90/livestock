# app/utils/paystack_utils.py

import requests

def verify_paystack_transaction(reference):
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer YOUR_SECRET_KEY",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers)
        response_data = response.json()

        if response_data['status'] and response_data['data']['status'] == 'success':
            return response_data['data']
        return None
    except Exception as e:
        print("Paystack verification error:", e)
        return None

# app/utils/paystack_utils.py

import requests

PAYSTACK_SECRET_KEY = "YOUR_SECRET_KEY"

def initiate_paystack_transfer(recipient_code, amount_naira, reason="Wallet Withdrawal"):
    """
    Initiates a transfer to a Paystack recipient.
    amount_naira: integer (₦ amount)
    recipient_code: recipient code from Paystack
    """
    url = "https://api.paystack.co/transfer"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "source": "balance",
        "amount": int(amount_naira * 100),  # Convert to kobo
        "recipient": recipient_code,
        "reason": reason
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        return data
    except Exception as e:
        print("Paystack transfer error:", e)
        return {"status": False, "message": str(e)}
