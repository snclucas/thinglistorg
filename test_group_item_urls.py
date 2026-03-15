#!/usr/bin/env python
"""Test script to verify group item URL functionality"""

from app import app, db
from models import User, Group, List, Item
from list_item_routes import get_item_url, get_list_url

def test_group_item_url():
    """Test that items in group lists get the correct URL"""
    with app.app_context():
        with app.test_request_context():
            # Create test user
            user = User.query.filter_by(email='test@example.com').first()
            if not user:
                user = User(email='test@example.com', username='testuser', password='test')
                db.session.add(user)
                db.session.flush()
            
            # Create test group
            group = Group(name='Test Group', owner_id=user.id)
            db.session.add(group)
            db.session.flush()
            
            # Create test list in group
            group_list = List(
                name='Test Group List',
                user_id=user.id,
                group_id=group.id,
                visibility='private'
            )
            db.session.add(group_list)
            db.session.flush()
            
            # Create test item in group list
            item = Item(
                name='Test Group Item',
                list_id=group_list.id
            )
            db.session.add(item)
            db.session.flush()
            db.session.commit()
            
            # Force slug generation by reloading
            db.session.refresh(group)
            db.session.refresh(group_list)
            db.session.refresh(item)
            
            # Test URLs
            print(f"\nGroup slug: {group.slug} (id: {group.id})")
            print(f"List slug: {group_list.slug} (id: {group_list.id})")
            print(f"Item slug: {item.slug} (id: {item.id})")
            
            # Test get_item_url for group item
            item_url = get_item_url(item)
            print(f"\nItem URL (view): {item_url}")
            
            # Expected pattern uses IDs since slugs might not be generated yet
            expected_pattern = f"/{group.id}/{group_list.id}/{item.id}"
            print(f"Expected pattern: {expected_pattern}")
            
            # URL should use IDs at minimum
            assert str(group.id) in item_url, f"Group ID not in URL: {item_url}"
            assert str(group_list.id) in item_url, f"List ID not in URL: {item_url}"
            assert str(item.id) in item_url, f"Item ID not in URL: {item_url}"
            
            # Test edit URL
            edit_url = get_item_url(item, endpoint='list_item.edit_item')
            print(f"Item URL (edit): {edit_url}")
            assert "/edit" in edit_url, f"Edit endpoint not found in URL: {edit_url}"
            
            # Test delete URL
            delete_url = get_item_url(item, endpoint='list_item.delete_item')
            print(f"Item URL (delete): {delete_url}")
            assert "/delete" in delete_url, f"Delete endpoint not found in URL: {delete_url}"
            
            # Test personal list item
            personal_list = List(
                name='Test Personal List',
                user_id=user.id,
                visibility='private'
            )
            db.session.add(personal_list)
            db.session.flush()
            
            personal_item = Item(
                name='Test Personal Item',
                list_id=personal_list.id
            )
            db.session.add(personal_item)
            db.session.flush()
            db.session.commit()
            
            personal_url = get_item_url(personal_item)
            print(f"\nPersonal item URL: {personal_url}")
            print(f"Should use url_for pattern (contains /items/)")
            assert "/items/" in personal_url, f"Personal item URL should contain /items/: {personal_url}"
            
            # Cleanup
            db.session.delete(item)
            db.session.delete(personal_item)
            db.session.delete(group_list)
            db.session.delete(personal_list)
            db.session.delete(group)
            db.session.commit()
            
            print("\n✓ All tests passed!")

if __name__ == '__main__':
    test_group_item_url()
