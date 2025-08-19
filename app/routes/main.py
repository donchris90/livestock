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

    # Start base query
    query = db.session.query(Product).options(joinedload(Product.owner)).filter(Product.is_deleted == False)


    # Apply filters
    if q:
        query = query.filter(
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
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if state:
        query = query.filter(Product.state.ilike(f"%{state}%"))
    if city:
        query = query.filter(Product.city.ilike(f"%{city}%"))

    try:
        if min_price:
            query = query.filter(Product.price >= float(min_price))
        if max_price:
            query = query.filter(Product.price <= float(max_price))
    except ValueError:
        flash("Invalid price range", "warning")

    # 🎯 Order promoted products first
    query = query.filter(
        or_(Product.promotion_end_date == None, Product.promotion_end_date > now)
    )

    products = query.order_by(
        Product.is_featured.desc(),
        Product.is_top.desc(),
        Product.boost_score.desc(),
        Product.created_at.desc()
    ).all()

    # 🌟 Featured products
    featured_products = Product.query.filter(
        Product.is_featured == True,
        Product.promotion_end_date > now,
        Product.is_deleted == False
    ).order_by(Product.promotion_end_date.desc()).limit(10).all()

    # 📌 Top products
    top_products = Product.query.filter(
        Product.is_top == True,
        Product.promotion_end_date > now,
        Product.is_deleted == False
    ).order_by(Product.promotion_end_date.desc()).limit(10).all()

    # 📦 Regular products
    regular_products = Product.query.filter(
        (Product.is_featured == False) | (Product.promotion_end_date == None),
        (Product.is_top == False),
        Product.is_deleted == False
    ).order_by(Product.created_at.desc()).all()

    promote_product = products[0] if products else None

    return render_template(
        "home.html",
        products=products,
        featured_products=featured_products,
        top_products=top_products,
        regular_products=regular_products,
        promote_product=promote_product,
        now=datetime.utcnow()# ✅ Add this line to fix the UndefinedError
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

