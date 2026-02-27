#!/usr/bin/env python
"""
Development server runner for ThingList
"""
import os
from app import app, db

if __name__ == '__main__':
    # Create application context and database tables
    with app.app_context():
        db.create_all()
        print("✓ Database tables initialized")

    print("\n" + "="*50)
    print("ThingList - User Authentication System")
    print("="*50)
    print("\n✓ Starting development server...")
    print("✓ Access the application at: http://localhost:5000")
    print("✓ Press CTRL+C to stop the server")
    print("\n" + "="*50 + "\n")

    # Run the application
    app.run(debug=True, host='127.0.0.1', port=5000)

