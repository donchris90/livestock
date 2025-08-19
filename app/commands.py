# app/commands.py
import click
from app.extensions import db
from app.models import SubscriptionPlan

def register_commands(app):
    @app.cli.command("seed-plans")
    def seed_plans():
        plans = [
            SubscriptionPlan(name='Starter', price=100, upload_limit=10, boost_score=5, featured=False, duration_days=30),
            SubscriptionPlan(name='Pro', price=300, upload_limit=50, boost_score=20, featured=True, duration_days=60),
            SubscriptionPlan(name='Premium', price=500, upload_limit=None, boost_score=50, featured=True, duration_days=90),
        ]
        db.session.bulk_save_objects(plans)
        db.session.commit()
        click.echo("✅ Subscription plans seeded successfully.")
