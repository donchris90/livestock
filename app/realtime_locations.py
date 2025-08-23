import redis
import json
from datetime import datetime

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def update_user_location(user_id, role, latitude, longitude):
    """
    Store location in Redis with expiry (e.g., 1 minute).
    """
    key = f"{role}:{user_id}"
    data = {
        "user_id": user_id,
        "latitude": latitude,
        "longitude": longitude,
        "last_seen": datetime.utcnow().isoformat()
    }
    r.set(key, json.dumps(data), ex=60)  # expires in 60 sec

def get_nearby_users(role, latitude, longitude, radius_km=10):
    """
    Return all users of this role within a radius (naive linear scan).
    For production, use geospatial Redis commands.
    """
    nearby = []
    for key in r.keys(f"{role}:*"):
        user_data = json.loads(r.get(key))
        lat2, lon2 = user_data["latitude"], user_data["longitude"]
        if haversine(latitude, longitude, lat2, lon2) <= radius_km:
            nearby.append(user_data)
    return nearby

def haversine(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c
