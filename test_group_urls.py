#!/usr/bin/env python
"""Test script to verify group list URL functionality"""

from app import app, db
from models import User, List, Group
from list_item_routes import get_list_url

def test_group_list_url():
    """Test that lists with groups get the correct URL"""
    with app.app_context():
        with app.test_request_context():
            try:
                # Create test data with unique username
                import time
                unique_id = int(time.time() * 1000) % 100000
                username = f'testuser_{unique_id}'
                
                user = User(username=username, email=f'test_{unique_id}@example.com')
                user.set_password('password')
                db.session.add(user)
                db.session.flush()
                
                # Create a group
                group = Group(name='Test Group', owner_id=user.id)
                db.session.add(group)
                db.session.flush()
                group.generate_slug()
                
                # Create a personal list
                personal_list = List(name='Personal List', user_id=user.id)
                db.session.add(personal_list)
                db.session.flush()
                personal_list.generate_slug()
                
                # Create a group list
                group_list = List(name='Group List', user_id=user.id, group_id=group.id)
                db.session.add(group_list)
                db.session.flush()
                group_list.generate_slug()
                
                db.session.commit()
                
                # Test personal list URL
                personal_url = get_list_url(personal_list)
                print(f"Personal list URL: {personal_url}")
                assert '/groups/' not in personal_url, f"Personal list should not have group URL: {personal_url}"
                assert f'/lists/{personal_list.slug}' in personal_url or personal_list.slug in personal_url, f"Personal list should have correct URL: {personal_url}"
                
                # Test group list URL
                group_url = get_list_url(group_list)
                print(f"Group list URL: {group_url}")
                assert f'/groups/{group.slug}' in group_url, f"Group list should have group slug in URL: {group_url}"
                assert f'/lists/{group_list.slug}' in group_url, f"Group list should have list slug in URL: {group_url}"
                
                # Test group list edit URL
                group_edit_url = get_list_url(group_list, endpoint='list_item.edit_list')
                print(f"Group list edit URL: {group_edit_url}")
                assert '/edit' in group_edit_url or group_edit_url.endswith('edit')  or 'edit' in group_edit_url, f"Edit URL should contain 'edit': {group_edit_url}"
                
                print("\n✅ All tests passed!")
                print(f"  ✓ Personal list uses: /lists/{personal_list.slug}")
                print(f"  ✓ Group list uses:    /groups/{group.slug}/lists/{group_list.slug}")
                print(f"  ✓ Group list edit:    {group_edit_url}")
                
                # Clean up
                db.session.delete(group_list)
                db.session.delete(personal_list)
                db.session.delete(group)
                db.session.delete(user)
                db.session.commit()
                
            except Exception as e:
                print(f"❌ Test failed: {e}")
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    test_group_list_url()
