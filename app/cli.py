from app.extensions import db
from app.models import Product
from datetime import datetime
from flask import current_app
import click

@current_app.cli.command("clear_expired_boosts")
def clear_expired_boosts():
    now = datetime.utcnow()
    expired = Product.query.filter(Product.boost_expiry < now, Product.is_boosted == True).all()
    for product in expired:
        product.is_boosted = False
    db.session.commit()
    print(f"✅ Cleared {len(expired)} expired boosts")
