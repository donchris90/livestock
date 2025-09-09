from flask import Blueprint, Response, url_for
from datetime import datetime

# Assuming you already have models like Product, User
from app.models import Product, User, db

sitemap_bp = Blueprint("sitemap", __name__)

@sitemap_bp.route("/sitemap.xml", methods=["GET"])
def sitemap():
    pages = []

    # --- Static pages ---
    ten_days_ago = (datetime.now()).date().isoformat()
    static_pages = [
        {"loc": url_for("marketplace.homepage", _external=True), "lastmod": ten_days_ago},
        {"loc": url_for("auth.login", _external=True), "lastmod": ten_days_ago},
        {"loc": url_for("auth.register", _external=True), "lastmod": ten_days_ago},
        {"loc": url_for("main.about", _external=True), "lastmod": ten_days_ago},
        {"loc": url_for("main.contact", _external=True), "lastmod": ten_days_ago},
    ]
    pages.extend(static_pages)

    # --- Dynamic product pages ---
    products = Product.query.filter_by(is_deleted=False).all()
    for product in products:
        pages.append({
            "loc": url_for("marketplace.product_detail", product_id=product.id, _external=True),
            "lastmod": (product.updated_at or product.created_at).date().isoformat()
        })

    # --- Dynamic agent/logistics/vet profiles ---
    users = User.query.filter(User.role.in_(["agent", "logistics", "vet"])).all()
    for user in users:
        pages.append({
            "loc": url_for("user.profile", user_id=user.id, _external=True),
            "lastmod": datetime.now().date().isoformat()
        })

    # --- Generate XML ---
    xml = render_sitemap(pages)

    return Response(xml, mimetype="application/xml")


def render_sitemap(pages):
    """Render XML sitemap string from list of pages"""
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for page in pages:
        xml.append("  <url>")
        xml.append(f"    <loc>{page['loc']}</loc>")
        xml.append(f"    <lastmod>{page['lastmod']}</lastmod>")
        xml.append("    <changefreq>weekly</changefreq>")
        xml.append("    <priority>0.8</priority>")
        xml.append("  </url>")

    xml.append("</urlset>")
    return "\n".join(xml)
