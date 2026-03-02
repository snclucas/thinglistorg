"""
Test utilities and helpers for ThingList application tests.

Provides:
- Test data factories
- Common assertion helpers
- Request utilities
- Database utilities
"""

import json
from models import db, User, List, Item, Group, GroupMember, Location, ItemType


class TestDataFactory:
    """Factory for creating test data."""

    @staticmethod
    def create_user(username='testuser', email='test@example.com', password='TestPass123!'):
        """Create a test user."""
        user = User(
            username=username,
            email=email,
            email_verified=True,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def create_list(name='Test List', user_id=None, is_public=False):
        """Create a test list."""
        if user_id is None:
            raise ValueError("user_id is required")
        
        test_list = List(
            name=name,
            user_id=user_id,
            is_public=is_public
        )
        db.session.add(test_list)
        db.session.commit()
        return test_list

    @staticmethod
    def create_item(name='Test Item', list_id=None, quantity=1, notes=''):
        """Create a test item."""
        if list_id is None:
            raise ValueError("list_id is required")
        
        item = Item(
            name=name,
            list_id=list_id,
            quantity=quantity,
            notes=notes
        )
        db.session.add(item)
        db.session.commit()
        return item

    @staticmethod
    def create_group(name='Test Group', owner_id=None):
        """Create a test group."""
        if owner_id is None:
            raise ValueError("owner_id is required")
        
        group = Group(
            name=name,
            owner_id=owner_id
        )
        db.session.add(group)
        db.session.commit()
        return group

    @staticmethod
    def create_item_type(name='Test Type', user_id=None):
        """Create a test item type."""
        if user_id is None:
            raise ValueError("user_id is required")
        
        item_type = ItemType(
            name=name,
            user_id=user_id
        )
        db.session.add(item_type)
        db.session.commit()
        return item_type

    @staticmethod
    def create_location(name='Test Location', user_id=None):
        """Create a test location."""
        if user_id is None:
            raise ValueError("user_id is required")
        
        location = Location(
            name=name,
            user_id=user_id
        )
        db.session.add(location)
        db.session.commit()
        return location

    @staticmethod
    def create_group_member(group_id, user_id, role='member'):
        """Add a member to a group."""
        member = GroupMember(
            group_id=group_id,
            user_id=user_id,
            role=role
        )
        db.session.add(member)
        db.session.commit()
        return member


class AssertionHelpers:
    """Helper methods for common assertions."""

    @staticmethod
    def assert_successful_response(response, status_code=200):
        """Assert response is successful."""
        assert response.status_code == status_code, \
            f"Expected status {status_code}, got {response.status_code}. Response: {response.data}"

    @staticmethod
    def assert_redirect_response(response, expected_location=None):
        """Assert response is a redirect."""
        assert response.status_code in [301, 302, 303, 307, 308], \
            f"Expected redirect status, got {response.status_code}"
        
        if expected_location:
            assert expected_location in response.location, \
                f"Expected redirect to {expected_location}, got {response.location}"

    @staticmethod
    def assert_json_response(response, expected_status=200):
        """Assert response is valid JSON."""
        assert response.status_code == expected_status
        assert response.content_type == 'application/json'
        
        try:
            return json.loads(response.data)
        except json.JSONDecodeError:
            raise AssertionError(f"Response is not valid JSON: {response.data}")

    @staticmethod
    def assert_error_response(response, expected_status=400):
        """Assert response is an error."""
        assert response.status_code == expected_status, \
            f"Expected status {expected_status}, got {response.status_code}"

    @staticmethod
    def assert_unauthorized(response):
        """Assert response indicates unauthorized access."""
        assert response.status_code in [301, 302, 401, 403], \
            f"Expected unauthorized response, got {response.status_code}"

    @staticmethod
    def assert_not_found(response):
        """Assert response is 404 Not Found."""
        assert response.status_code == 404

    @staticmethod
    def assert_contains_text(response, text):
        """Assert response contains text."""
        assert text.encode() in response.data or text in response.data.decode(), \
            f"Response does not contain '{text}'"

    @staticmethod
    def assert_not_contains_text(response, text):
        """Assert response does not contain text."""
        assert text.encode() not in response.data and text not in response.data.decode(), \
            f"Response contains unexpected text '{text}'"


class HttpHelpers:
    """Helper methods for HTTP requests."""

    @staticmethod
    def login(client, username='testuser', password='TestPass123!'):
        """Helper to login a user."""
        from flask import url_for
        return client.post(
            url_for('auth.login'),
            data={
                'username': username,
                'password': password
            },
            follow_redirects=True
        )

    @staticmethod
    def logout(client):
        """Helper to logout a user."""
        from flask import url_for
        return client.get(url_for('auth.logout'), follow_redirects=True)

    @staticmethod
    def post_json(client, url, data):
        """Helper to POST JSON data."""
        return client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

    @staticmethod
    def get_json_response(client, url, query_string=None):
        """Helper to GET and parse JSON response."""
        response = client.get(url, query_string=query_string or {})
        return json.loads(response.data)


class DatabaseHelpers:
    """Helper methods for database operations."""

    @staticmethod
    def clear_all_tables():
        """Clear all database tables."""
        db.drop_all()
        db.create_all()

    @staticmethod
    def count_users():
        """Count total users."""
        return User.query.count()

    @staticmethod
    def count_lists():
        """Count total lists."""
        return List.query.count()

    @staticmethod
    def count_items():
        """Count total items."""
        return Item.query.count()

    @staticmethod
    def get_user_by_username(username):
        """Get user by username."""
        return User.query.filter_by(username=username).first()

    @staticmethod
    def get_list_by_name(name):
        """Get list by name."""
        return List.query.filter_by(name=name).first()

    @staticmethod
    def get_item_by_name(name):
        """Get item by name."""
        return Item.query.filter_by(name=name).first()

    @staticmethod
    def reset_sequences():
        """Reset database sequences (for SQLite, no-op)."""
        pass
