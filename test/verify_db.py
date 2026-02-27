#!/usr/bin/env python
"""Test database initialization and schema"""
import sys

try:
    from app import app, db
    from models import User, List, Item, ItemType

    with app.app_context():
        # Create all tables first
        print("Creating database tables...")
        db.create_all()

        # Initialize system item types
        print("Initializing system item types...")
        system_types = [
            'Appliance', 'Electronics', 'Furniture', 'Clothing', 'Books',
            'Kitchen', 'Tools', 'Sports', 'Toys', 'Decorations',
            'Office', 'Garden', 'Bedding', 'Dishes', 'Cleaning'
        ]

        for type_name in system_types:
            existing = ItemType.query.filter_by(name=type_name, is_system=True).first()
            if not existing:
                item_type = ItemType(name=type_name, is_system=True, user_id=None)
                db.session.add(item_type)

        db.session.commit()

        # Verify
        item_type_count = ItemType.query.filter_by(is_system=True).count()
        print(f"\n✓ Successfully initialized")
        print(f"✓ Item types: {item_type_count}")
        print(f"\n✓ Database is ready to use!")

except Exception as e:
    print(f"\n✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

