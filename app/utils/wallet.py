from app.models import Wallet, db

def get_or_create_wallet(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if wallet:
        return wallet
    wallet = Wallet(user_id=user_id, balance=0.0)
    db.session.add(wallet)
    db.session.commit()
    return wallet
