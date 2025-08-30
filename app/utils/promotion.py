def get_price_for_promo(promo_type):
    PROMOTION_PRICING = {
        "featured": {7: 500, 30: 1500, 60: 2500},
        "boosted": {7: 1000, 30: 2500, 60: 4000},
        "top": {7: 1500, 30: 3000, 60: 5000}
    }
    return PROMOTION_PRICING.get(promo_type)


import random
from datetime import datetime
from sqlalchemy import or_
from app.models import Product
from app.extensions import db

def get_rotated_featured(limit=20):
    # Get all featured products
    featured_products = Product.query.filter_by(is_featured=True).all()

    if len(featured_products) <= limit:
        return featured_products

    # Sort by last_shown (oldest first → priority to rotate in)
    featured_products.sort(key=lambda p: p.last_shown or datetime(2000, 1, 1))

    # Pick the first `limit` items
    selected = featured_products[:limit]

    # Update last_shown for fairness
    for product in selected:
        product.last_shown = datetime.utcnow()
    db.session.commit()

    return selected


def get_rotated_boosted(limit=25):
    boosted_products = Product.query.filter_by(is_boosted=True).all()

    if len(boosted_products) <= limit:
        return boosted_products

    boosted_products.sort(key=lambda p: p.last_shown or datetime(2000, 1, 1))
    selected = boosted_products[:limit]

    for product in selected:
        product.last_shown = datetime.utcnow()
    db.session.commit()

    return selected
