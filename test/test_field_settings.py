#!/usr/bin/env python
"""Test script to verify field settings are saved to the database"""

from app import app, db
from models import List, User

def test_field_settings():
    with app.app_context():
        # Get or create a test user
        test_user = User.query.filter_by(username='testuser').first()
        if not test_user:
            test_user = User(username='testuser', email='test@example.com')
            test_user.set_password('password123')
            db.session.add(test_user)
            db.session.commit()
            print(f"Created test user: {test_user.username}")
        
        # Get or create a test list
        test_list = List.query.filter_by(user_id=test_user.id, name='Test List').first()
        if not test_list:
            test_list = List(name='Test List', user_id=test_user.id)
            db.session.add(test_list)
            db.session.commit()
            print(f"Created test list: {test_list.name}")
        
        # Test 1: Set some fields to hidden
        print("\n=== Test 1: Setting description field to hidden ===")
        field_settings = {
            'name': {'visible': True, 'editable': True},
            'description': {'visible': False, 'editable': False},  # Hidden
            'notes': {'visible': True, 'editable': True},
            'quantity': {'visible': True, 'editable': True},
            'low_stock_threshold': {'visible': True, 'editable': True},
            'item_type': {'visible': True, 'editable': True},
            'location': {'visible': True, 'editable': True},
            'barcode': {'visible': True, 'editable': True},
            'url': {'visible': True, 'editable': True},
            'tags': {'visible': True, 'editable': True},
            'reminder_at': {'visible': True, 'editable': True},
            'attachments': {'visible': True, 'editable': True}
        }
        
        test_list.set_field_settings(field_settings)
        
        # This is the critical fix - mark the settings column as modified
        from sqlalchemy.orm import attributes
        attributes.flag_modified(test_list, 'settings')
        
        db.session.commit()
        
        print(f"Settings after save: {test_list.settings}")
        print(f"get_field_settings() result: {test_list.get_field_settings()}")
        
        # Refresh from database to verify it was actually saved
        db.session.refresh(test_list)
        print(f"Settings from DB after refresh: {test_list.settings}")
        print(f"Description visible? {test_list.is_field_visible('description')}")
        print(f"Description editable? {test_list.is_field_editable('description')}")
        
        assert test_list.is_field_visible('description') == False, "Description should be hidden!"
        assert test_list.is_field_editable('description') == False, "Description should not be editable!"
        print("✓ Test 1 PASSED: Description field is correctly hidden")
        
        # Test 2: Re-enable the description field
        print("\n=== Test 2: Re-enabling description field ===")
        field_settings['description'] = {'visible': True, 'editable': True}
        test_list.set_field_settings(field_settings)
        attributes.flag_modified(test_list, 'settings')
        db.session.commit()
        
        db.session.refresh(test_list)
        print(f"Description visible? {test_list.is_field_visible('description')}")
        print(f"Description editable? {test_list.is_field_editable('description')}")
        
        assert test_list.is_field_visible('description') == True, "Description should be visible!"
        assert test_list.is_field_editable('description') == True, "Description should be editable!"
        print("✓ Test 2 PASSED: Description field is correctly re-enabled")
        
        print("\n✓ All tests passed!")

if __name__ == '__main__':
    test_field_settings()

