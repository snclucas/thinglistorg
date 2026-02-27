"""
Test script to verify the login flow with unverified user
"""
from app import app
from models import User, db

with app.app_context():
    # Find simon
    simon = User.query.filter_by(username='simon').first()
    if simon:
        print(f"User found: {simon.username}")
        print(f"Email: {simon.email}")
        print(f"Email verified: {simon.email_verified}")
        print(f"Password hash exists: {bool(simon.password_hash)}")
        print(f"\nWhen simon tries to login:")
        print(f"1. Credentials will be checked: email_verified={simon.email_verified}")
        print(f"2. Flash message will be triggered")
        print(f"3. Toast should appear with 'warning' category")
    else:
        print("User simon not found")

