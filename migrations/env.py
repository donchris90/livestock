import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')

    # ✅ Always use the EXTERNAL Render DB URL when working locally
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://livestock:UfgXHMMXLBr5y22ZaYWBOfrI99vFENvH@dpg-d28ve4mr433s73c1a2hg-a.oregon-postgres.render.com/livestockdb_33g0'
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
