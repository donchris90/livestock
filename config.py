import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key")

    # Ensure SQLAlchemy uses psycopg3
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300
    }

    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'app', 'static', 'uploads')
    INSPECTION_UPLOAD_FOLDER = 'app/static/uploads/inspection_files'

    # Payment keys
    FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY')
    FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY')
    FLUTTERWAVE_ENCRYPTION_KEY = os.getenv('FLUTTERWAVE_ENCRYPTION_KEY')

    PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
    PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
