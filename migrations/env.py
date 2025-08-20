import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')

    # Get the Render DATABASE_URL and force psycopg3
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql://livestock:UfgXHMMXLBr5y22ZaYWBOfrI99vFENvH@dpg-d28ve4mr433s73c1a2hg-a.oregon-postgres.render.com:5432/livestockdb_33g0'
    )

    # Replace postgres:// with postgresql+psycopg:// to use psycopg3
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
