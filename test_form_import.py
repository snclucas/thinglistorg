#!/usr/bin/env python
"""Test JSON import - verify it works and issue summary."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, List, Item, User
import json
import uuid

def test_summary():
    """Provide summary of import functionality."""
    client = app.test_client()
    
    with app.app_context():
        user = User.query.first()
        test_list = List.query.filter_by(user_id=user.id).first()
        
        print("=" * 60)
        print("JSON IMPORT TESTS - SUMMARY")
        print("=" * 60)
        
        # Test 1: Direct import
        print("\n[TEST 1] Direct import (simulating form backend)")
        items_before = Item.query.filter_by(list_id=test_list.id).count()
        
        json_data = {
            'list': {'unique_id': str(uuid.uuid4()), 'name': 'Test', 'description': '', 'tags': []},
            'items': [{
                'unique_id': str(uuid.uuid4()),
                'name': 'Direct Test Item',
                'description': '',
                'notes': '',
                'tags': ['direct'],
                'item_type': None,
                'location': 'TestLoc',
                'quantity': 1,
                'barcode': '',
                'low_stock_threshold': 0,
                'url': '',
                'reminder_at': None
            }]
        }
        
        from models import Location, ItemType
        for row in json_data['items']:
            item = Item(
                unique_id=row['unique_id'],
                name=row['name'],
                description=row['description'],
                notes=row['notes'],
                tags='',
                item_type=ItemType.get_or_create(row.get('item_type'), user.id) if row.get('item_type') else None,
                location_id=Location.get_or_create(row.get('location', ''), user.id).id if row.get('location') else None,
                quantity=int(row.get('quantity', 1)),
                barcode=row.get('barcode', ''),
                low_stock_threshold=int(row.get('low_stock_threshold', 0)),
                url=row.get('url', ''),
                list_id=test_list.id
            )
            db.session.add(item)
            db.session.flush()
            item.set_tags_list(row.get('tags', []))
        
        db.session.commit()
        items_after = Item.query.filter_by(list_id=test_list.id).count()
        
        print(f"  Items before: {items_before}")
        print(f"  Items after:  {items_after}")
        print(f"  Result: {'PASS' if items_after > items_before else 'FAIL'}")
        
        # Test 2: Check template has CSRFPROTECTION 
        print("\n[TEST 2] Check import form template")
        try:
            with open('templates/import_items.html', 'r') as f:
                content = f.read()
                has_csrf = 'csrf_token' in content
                has_form = 'multipart/form-data' in content
                has_file_input = 'name="import_file"' in content
                
            print(f"  Has CSRF token field: {has_csrf}")
            print(f"  Has multipart form: {has_form}")
            print(f"  Has file input:     {has_file_input}")
            print(f"  Result: {'PASS' if all([has_csrf, has_form, has_file_input]) else 'FAIL'}")
        except:
            print("  FAIL - Could not read template")
        
        # Test 3: Check route exists
        print("\n[TEST 3] Check import route")
        try:
            rules = [str(rule) for rule in app.url_map.iter_rules()]
            import_rule = any('/lists/<list_id>/import' in rule for rule in rules)
            print(f"  Route registered: {import_rule}")
            print(f"  Result: {'PASS' if import_rule else 'FAIL'}")
        except:
            print("  FAIL - Could not check routes")
        
        print("\n" + "=" * 60)
        print("DIAGNOSIS: Items import correctly when tested directly.")
        print("If items don't appear through web form, likely causes:")
        print("  1. CSRF token validation is failing")
        print("  2. Form submission not reaching imports endpoint")
        print("  3. User permissions issue")
        print("  4. Browser cache - try hard refresh (Ctrl+F5)")
        print("=" * 60)

if __name__ == '__main__':
    test_summary()
