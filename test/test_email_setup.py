from app import app
from models import User, db

with app.app_context():
    user = User.query.first()
    print('✅ App and database working!')
    print(f'   Sample user: {user.username} ({user.email})')
    print(f'   Email verified: {user.email_verified}')

