import redis
import json
import os
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

# Redis setup using environment variables (Render)
REDIS_HOST = "redis-18156.c239.us-east-1-2.ec2.redns.redis-cloud.com"
REDIS_PORT = 18156
REDIS_PASSWORD = "9b3Kj1TAgQDlVxHXHJrPGaTnIy4lgMbZ"

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True
)

def update_user_location(user_id, role, latitude, longitude, expiry_sec=60):
    """
    Store location in Redis with optional expiry (default: 60 seconds).
    """
    key = f"{role}:{user_id}"
    data = {
        "user_id": user_id,
        "latitude": latitude,
        "longitude": longitude,
        "last_seen": datetime.utcnow().isoformat()
    }
    r.set(key, json.dumps(data), ex=expiry_sec)

def get_nearby_users(role, latitude, longitude, radius_km=10):
    """
    Return all users of this role within a radius (naive linear scan).
    For production, consider Redis GEO commands.
    """
    nearby = []
    for key in r.keys(f"{role}:*"):
        user_data = json.loads(r.get(key))
        lat2, lon2 = float(user_data["latitude"]), float(user_data["longitude"])
        if haversine(latitude, longitude, lat2, lon2) <= radius_km:
            nearby.append(user_data)
    return nearby

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on the Earth.
    """
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c
