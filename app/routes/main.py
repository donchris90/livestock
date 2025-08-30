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

    # Base query: all active products
    base_query = Product.query.options(joinedload(Product.owner)).filter(Product.is_deleted == False)

    # Apply search filters
    if q:
        base_query = base_query.filter(
            or_(
                Product.title.ilike(f"%{q}%"),
                Product.description.ilike(f"%{q}%"),
                Product.category.ilike(f"%{q}%"),
                Product.type.ilike(f"%{q}%"),
                Product.city.ilike(f"%{q}%"),
                Product.state.ilike(f"%{q}%")
            )
        )
    if category:
        base_query = base_query.filter(Product.category.ilike(f"%{category}%"))
    if state:
        base_query = base_query.filter(Product.state.ilike(f"%{state}%"))
    if city:
        base_query = base_query.filter(Product.city.ilike(f"%{city}%"))

    # Price filter
    try:
        if min_price:
            base_query = base_query.filter(Product.price >= float(min_price))
        if max_price:
            base_query = base_query.filter(Product.price <= float(max_price))
    except ValueError:
        flash("Invalid price range", "warning")

    # Only active promotions
    base_query = base_query.filter(or_(Product.promotion_end_date == None, Product.promotion_end_date > now))

    # Fetch all products
    all_products = base_query.order_by(
        Product.is_boosted.desc(),
        Product.is_featured.desc(),
        Product.is_top.desc(),
        Product.created_at.desc()
    ).all()

    # Convert photos string to list if needed
    for p in all_products:
        if isinstance(p.photos, str):
            p.photos = p.photos.strip("{}").replace('"', '').split(",")

    # Combine all products into one prioritized list
    sorted_products = (
            [p for p in all_products if p.is_boosted] +
            [p for p in all_products if p.is_featured and not p.is_boosted] +
            [p for p in all_products if p.is_top and not (p.is_boosted or p.is_featured)] +
            [p for p in all_products if not (p.is_boosted or p.is_featured or p.is_top)]
    )

    return render_template(
        "home.html",
        sorted_products=sorted_products,
        now=now
    )


@main_bp.route('/agents')
def view_agents():
    return render_template('search_agents.html')



@main_bp.route('/vets')
def view_vets():
    return render_template('vets.html')

@main_bp.route('/logistics')
def view_logistics():
    return render_template('logistics.html')

