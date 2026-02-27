#!/usr/bin/env python
"""Test that the app can query items without errors"""

from app import app, db
from models import Item, List, ItemType

with app.app_context():
    try:
        # Try to query items - this will fail if item_type_id column doesn't exist
        items = Item.query.all()
        print(f"SUCCESS: Database is ready!")
        print(f"Total items in database: {len(items)}")

        # Check item types
        types = ItemType.query.filter_by(is_system=True).count()
        print(f"System item types: {types}")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

