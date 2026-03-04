#!/usr/bin/env python
"""Debug script to test JSON import functionality."""

import json
import sys
import os

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, List, Item, Location, ItemType
from flask_login import login_user
import uuid

def test_import():
    """Test importing items into a list."""
    with app.app_context():
        # Create a test user
        user = User.query.first()
        if not user:
            user = User(username='testuser', email='test@example.com')
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            print(f"Created test user: {user.id}")
        
        # Create a test list
        test_list = List.query.filter_by(user_id=user.id).first()
        if not test_list:
            test_list = List(
                unique_id=str(uuid.uuid4()),
                name='Test List',
                user_id=user.id
            )
            db.session.add(test_list)
            db.session.commit()
            print(f"Created test list: {test_list.id}")
        
        # Create sample import data
        sample_data = {
            'list': {
                'unique_id': test_list.unique_id,
                'name': test_list.name,
                'description': test_list.description,
                'tags': []
            },
            'items': [
                {
                    'unique_id': str(uuid.uuid4()),
                    'name': 'Test Item 1',
                    'description': 'A test item',
                    'notes': 'Some notes',
                    'tags': ['tag1', 'tag2'],
                    'item_type': None,
                    'location': 'Kitchen',
                    'quantity': 5,
                    'barcode': '',
                    'low_stock_threshold': 2,
                    'url': '',
                    'reminder_at': None
                },
                {
                    'unique_id': str(uuid.uuid4()),
                    'name': 'Test Item 2',
                    'description': 'Another test item',
                    'notes': '',
                    'tags': ['tag3'],
                    'item_type': None,
                    'location': 'Bedroom',
                    'quantity': 10,
                    'barcode': '',
                    'low_stock_threshold': 0,
                    'url': '',
                    'reminder_at': None
                }
            ]
        }
        
        # Save sample JSON file
        json_file = '/tmp/test_import.json'
        with open(json_file, 'w') as f:
            json.dump(sample_data, f, indent=2)
        print(f"Created test JSON file: {json_file}")
        
        # Test the import
        print("\n=== Testing Import ===")
        imported = 0
        updated = 0
        skipped = 0
        
        for idx, row in enumerate(sample_data['items']):
            try:
                print(f"\nProcessing row {idx}: {row['name']}")
                name = (row.get('name') or '').strip()
                if not name:
                    print(f"  Skipped: no name")
                    continue
                
                unique_id = row.get('unique_id', '').strip()
                
                # Check if item exists
                existing_item = Item.query.filter_by(unique_id=unique_id, list_id=test_list.id).first()
                
                if not existing_item:
                    print(f"  Creating new item: {name}")
                    
                    # Get location
                    location_name = row.get('location') or ''
                    location_id = None
                    if location_name:
                        location = Location.get_or_create(location_name, user.id)
                        location_id = location.id
                        print(f"    Location: {location_name} (id={location_id})")
                    
                    # Create item
                    new_item = Item(
                        unique_id=unique_id,
                        name=name,
                        description=row.get('description') or '',
                        notes=row.get('notes') or '',
                        tags='',
                        item_type=None,
                        location_id=location_id,
                        quantity=int(row.get('quantity') or 1),
                        barcode=row.get('barcode') or '',
                        low_stock_threshold=int(row.get('low_stock_threshold') or 0),
                        url=row.get('url') or '',
                        list_id=test_list.id
                    )
                    print(f"    Item object created: {new_item}")
                    
                    db.session.add(new_item)
                    print(f"    Added to session")
                    
                    db.session.flush()
                    print(f"    Flushed to database, got id: {new_item.id}")
                    
                    # Set tags
                    tags_list = row.get('tags') or []
                    print(f"    Setting tags: {tags_list}")
                    new_item.set_tags_list(tags_list)
                    
                    imported += 1
                    print(f"  Success: imported")
            except Exception as e:
                import traceback
                print(f"  ERROR: {e}")
                print(traceback.format_exc())
                db.session.rollback()
                raise
        
        # Commit
        print(f"\nCommitting {imported} items...")
        db.session.commit()
        print(f"Commit successful!")
        
        # Verify
        items = Item.query.filter_by(list_id=test_list.id).all()
        print(f"\n=== Result ===")
        print(f"Items in list: {len(items)}")
        for item in items:
            print(f"  - {item.name} (id: {item.id}, tags: {item.get_tags_list()})")

if __name__ == '__main__':
    test_import()
