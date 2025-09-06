from flask import Blueprint, request, render_template, flash
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload  # ⬅️ Import this at the top
from datetime import datetime
from app.models import Product, db

main_bp = Blueprint('main', __name__)


@main_bp.route("/")
def home():
    now = datetime.utcnow()

    # Filters
    q = request.args.get("q", "").strip()
    category = request.args.get("category")
    state = request.args.get("state")
    city = request.args.get("city")
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")

    # Base query: all active products (not deleted)
    base_query = Product.query.options(joinedload(Product.owner)).filter(
        or_(Product.is_deleted == False, Product.is_deleted.is_(None))
    )

    # 🔍 Improved text search
    if q:
        search_terms = q.split()  # split into words
        search_filters = []
        for term in search_terms:
            like_term = f"%{term}%"
            search_filters.append(Product.title.ilike(like_term))
            search_filters.append(Product.description.ilike(like_term))
            search_filters.append(Product.category.ilike(like_term))
            search_filters.append(Product.type.ilike(like_term))
            search_filters.append(Product.city.ilike(like_term))
            search_filters.append(Product.state.ilike(like_term))

        base_query = base_query.filter(or_(*search_filters))

    # Category / State / City filters
    if category:
        base_query = base_query.filter(Product.category.ilike(f"%{category}%"))
    if state:
        base_query = base_query.filter(Product.state.ilike(f"%{state}%"))
    if city:
        base_query = base_query.filter(Product.city.ilike(f"%{city}%"))

    # 💰 Price filters
    try:
        if min_price:
            base_query = base_query.filter(Product.price >= float(min_price))
        if max_price:
            base_query = base_query.filter(Product.price <= float(max_price))
    except ValueError:
        flash("Invalid price range", "warning")

    # ✅ Finally, fetch products
    products = base_query.order_by(Product.created_at.desc()).all()

    # Get all products
    all_products = base_query.order_by(Product.created_at.desc()).all()

    # Convert photos string → list if needed
    for p in all_products:
        if isinstance(p.photos, str):
            p.photos = p.photos.strip("{}").replace('"', "").split(",")

    # Promotion checks: only keep active ones
    def is_boosted(p):
        return p.is_boosted and p.boost_expiry and p.boost_expiry >= now

    def is_featured(p):
        return p.is_featured and p.featured_expiry and p.featured_expiry >= now

    def is_top(p):
        return p.is_top and p.top_expiry and p.top_expiry >= now

    # Build sorted list
    sorted_products = (
        [p for p in all_products if is_boosted(p)] +
        [p for p in all_products if is_featured(p) and not is_boosted(p)] +
        [p for p in all_products if is_top(p) and not (is_boosted(p) or is_featured(p))] +
        [p for p in all_products if not (is_boosted(p) or is_featured(p) or is_top(p))]
    )

    return render_template("home.html", sorted_products=sorted_products, now=now)






@main_bp.route('/agents')
def view_agents():
    return render_template('search_agents.html')



@main_bp.route('/vets')
def view_vets():
    return render_template('vets.html')

@main_bp.route('/logistics')
def view_logistics():
    return render_template('logistics.html')


# Terms of Use
@main_bp.route('/terms-of-use')
def terms_of_use():
    return render_template('terms-of-use.html')


# Privacy Policy
@main_bp.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy-policy.html')


# Refund Policy
@main_bp.route('/refund-policy')
def refund_policy():
    return render_template('refund-policy.html')