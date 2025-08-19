from geopy.geocoders import Nominatim
from app import create_app
from app.extensions import db
from app.models import User
import time

app = create_app()
geolocator = Nominatim(user_agent="livestock-app")

with app.app_context():
    users = User.query.filter((User.latitude == None) | (User.longitude == None)).all()

    for user in users:
        location_str = f"{user.city}, {user.state}, Nigeria"
        try:
            location = geolocator.geocode(location_str)
            if location:
                user.latitude = location.latitude
                user.longitude = location.longitude
                print(f"[✓] Updated {user.first_name} {user.last_name} → {location.latitude}, {location.longitude}")
            else:
                print(f"[✗] Could not find location: {location_str}")
        except Exception as e:
            print(f"[!] Error for {user.id}: {e}")
        time.sleep(1)  # To avoid being rate-limited

    db.session.commit()
    print("✅ Latitude and longitude update complete.")
