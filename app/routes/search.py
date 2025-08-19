from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from sqlalchemy import func
from app.models import User, Product
from app.extensions import db
from geopy.distance import geodesic
from math import radians, cos, sin, acos
import math
from datetime import datetime, timedelta
search_bp = Blueprint("search", __name__)

ONLINE_THRESHOLD = timedelta(minutes=5)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@search_bp.route("/search/agents", methods=["GET"])
def search_agents_view():
    state = request.args.get("state", "").strip().lower()
    city = request.args.get("city", "").strip().lower()
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)
    role = "agent"

    if not state or not city:
        return "State and city are required", 400

    agents = User.query.filter(
        User.role == role,
        func.lower(func.trim(User.state)) == state,
        func.lower(func.trim(User.city)) == city
    ).all()

    now = datetime.utcnow()
    agents_with_details = []

    for agent in agents:
        distance = None
        if user_lat is not None and user_lon is not None and agent.latitude and agent.longitude:
            try:
                distance = haversine(user_lat, user_lon, agent.latitude, agent.longitude)
                distance = round(distance, 2)
            except Exception:
                distance = None

        is_online = False
        if agent.last_seen:
            is_online = (now - agent.last_seen) < ONLINE_THRESHOLD

        agents_with_details.append({
            "agent": agent,
            "distance": distance,
            "is_online": is_online,

        })

    # Sort by distance (agents without distance go last)
    agents_with_details.sort(key=lambda x: x["distance"] if x["distance"] is not None else float('inf'))

    return render_template(
        "search_agents.html",
        agents=agents_with_details,
        city=city.title(),
        state=state.title(),
        now=now,

    )
@search_bp.route('/search-products')
def search_products():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius = request.args.get('radius', type=float, default=20)

    if lat is None or lon is None:
        return jsonify([])

    all_products = Product.query.all()
    nearby_products = []

    for p in all_products:
        if p.latitude and p.longitude:
            distance = geodesic((lat, lon), (p.latitude, p.longitude)).km
            if distance <= radius:
                nearby_products.append({
                    "id": p.id,
                    "title": p.title,
                    "distance": round(distance, 2),
                    "location": f"{p.state}, {p.city}",
                })

    return jsonify(nearby_products)

@search_bp.route('/search-users', methods=['GET'])
def search_users():
    role = request.args.get('role')  # e.g., 'agent' or 'logistics'
    lat = float(request.args.get('lat', 0))
    lon = float(request.args.get('lon', 0))
    radius_km = 50

    if not lat or not lon:
        return jsonify({'error': 'Missing coordinates'}), 400

    users = User.query.filter(User.role == role).all()
    nearby_users = []

    for user in users:
        if user.latitude and user.longitude:
            distance = haversine(lat, lon, user.latitude, user.longitude)
            if distance <= radius_km:
                nearby_users.append({
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'city': user.city,
                    'state': user.state,
                    'distance_km': round(distance, 2)
                })

    return jsonify({'users': nearby_users}), 200
from datetime import datetime, timedelta

ONLINE_THRESHOLD = timedelta(minutes=5)

@search_bp.route("/api/search-users")
def api_search_users():
    role = request.args.get("role", "").strip().lower()
    state = request.args.get("state", "").strip().lower()
    city = request.args.get("city", "").strip().lower()
    user_lat = request.args.get("lat", type=float)
    user_lon = request.args.get("lon", type=float)

    if not role or not state:
        return jsonify([])

    users_query = User.query.filter(
        User.role == role,
        db.func.lower(db.func.trim(User.state)) == state
    )

    if city:
        users_query = users_query.filter(
            db.func.lower(db.func.trim(User.city)) == city
        )

    users = users_query.all()

    now = datetime.utcnow()
    users_with_distance = []
    for u in users:
        dist = None
        if user_lat is not None and user_lon is not None and u.latitude and u.longitude:
            try:
                dist = haversine(user_lat, user_lon, u.latitude, u.longitude)
            except Exception:
                dist = None

        # Determine online status
        is_online = False
        if u.last_seen:
            is_online = (now - u.last_seen) < ONLINE_THRESHOLD

        users_with_distance.append((u, dist, is_online))

    # Sort users by distance ascending (None distances go last)
    users_with_distance.sort(key=lambda x: x[1] if x[1] is not None else float("inf"))

    result = []
    for u, dist, is_online in users_with_distance:
        result.append({
            "id": u.id,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": u.phone,
            "state": u.state,
            "city": u.city,
            "distance_km": round(dist, 2) if dist is not None else None,
            "is_online": is_online
        })

    return jsonify(result)




