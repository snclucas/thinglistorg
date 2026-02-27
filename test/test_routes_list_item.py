"""
Functional tests for list and item management routes.
"""
import pytest
from models import List, Item, db


class TestListRoutes:
    """Test list management routes."""

    def test_lists_page_requires_authentication(self, client):
        """Test that lists page requires authentication."""
        response = client.get('/lists', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_lists_page_authenticated(self, client, test_user, test_list, app):
        """Test lists page with authenticated user."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/lists')
                assert response.status_code == 200
                assert b'Test List' in response.data or b'Lists' in response.data

    def test_create_list_page_loads(self, client, test_user, app):
        """Test create list page loads."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/lists/create')
                assert response.status_code == 200
                assert b'Create' in response.data or b'List' in response.data

    def test_create_list_valid(self, client, test_user, app, db):
        """Test creating a valid list."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post('/lists/create', data={
                    'name': 'New Test List',
                    'description': 'A new list for testing',
                    'visibility': 'private',
                    'csrf_token': self._get_csrf_token(client, '/lists/create')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify list was created
                new_list = List.query.filter_by(name='New Test List').first()
                assert new_list is not None
                assert new_list.user_id == test_user.id

    def test_create_list_without_name(self, client, test_user, app):
        """Test creating list without name."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post('/lists/create', data={
                    'name': '',
                    'description': 'Missing name',
                    'visibility': 'private',
                    'csrf_token': self._get_csrf_token(client, '/lists/create')
                }, follow_redirects=True)

                assert response.status_code == 200
                assert b'Error' in response.data or b'required' in response.data

    def test_view_list_public(self, client, test_list, app):
        """Test viewing a public list."""
        test_list.visibility = 'public'
        with app.app_context():
            db.session.commit()

        response = client.get(f'/lists/{test_list.id}')
        assert response.status_code == 200
        assert test_list.name.encode() in response.data

    def test_view_list_private_without_auth(self, client, test_list):
        """Test viewing private list without authentication."""
        response = client.get(f'/lists/{test_list.id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_view_list_private_with_auth(self, client, test_user, test_list, app):
        """Test viewing private list with authentication as owner."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get(f'/lists/{test_list.id}')
                assert response.status_code == 200
                assert test_list.name.encode() in response.data

    def test_edit_list_as_owner(self, client, test_user, test_list, app, db):
        """Test editing list as owner."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/lists/{test_list.id}/edit', data={
                    'name': 'Updated List Name',
                    'description': 'Updated description',
                    'visibility': 'public',
                    'csrf_token': self._get_csrf_token(client, f'/lists/{test_list.id}/edit')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify list was updated
                updated_list = List.query.get(test_list.id)
                assert updated_list.name == 'Updated List Name'

    def test_delete_list_as_owner(self, client, test_user, test_list, app, db):
        """Test deleting list as owner."""
        list_id = test_list.id

        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/lists/{list_id}/delete', data={
                    'csrf_token': self._get_csrf_token(client, f'/lists/{list_id}')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify list was deleted
                deleted_list = List.query.get(list_id)
                assert deleted_list is None

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''


class TestItemRoutes:
    """Test item management routes."""

    def test_create_item_page_requires_auth(self, client, test_list):
        """Test that create item page requires authentication."""
        response = client.get(f'/lists/{test_list.id}/items/create', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_create_item_valid(self, client, test_user, test_list, app, db):
        """Test creating a valid item."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/lists/{test_list.id}/items/create', data={
                    'name': 'New Item',
                    'description': 'A test item',
                    'quantity': 5,
                    'location': 'Shelf A',
                    'csrf_token': self._get_csrf_token(client, f'/lists/{test_list.id}/items/create')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify item was created
                new_item = Item.query.filter_by(name='New Item').first()
                assert new_item is not None
                assert new_item.quantity == 5

    def test_view_item_requires_access(self, client, test_item):
        """Test viewing item requires list access."""
        response = client.get(f'/items/{test_item.id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_view_item_with_access(self, client, test_user, test_item, app):
        """Test viewing item with access."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get(f'/items/{test_item.id}')
                assert response.status_code == 200
                assert test_item.name.encode() in response.data

    def test_edit_item_as_owner(self, client, test_user, test_item, app, db):
        """Test editing item as owner."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/items/{test_item.id}/edit', data={
                    'name': 'Updated Item',
                    'quantity': 10,
                    'description': 'Updated description',
                    'csrf_token': self._get_csrf_token(client, f'/items/{test_item.id}/edit')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify item was updated
                updated_item = Item.query.get(test_item.id)
                assert updated_item.name == 'Updated Item'
                assert updated_item.quantity == 10

    def test_delete_item_as_owner(self, client, test_user, test_item, app, db):
        """Test deleting item as owner."""
        item_id = test_item.id

        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/items/{item_id}/delete', data={
                    'csrf_token': self._get_csrf_token(client, f'/items/{item_id}')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify item was deleted
                deleted_item = Item.query.get(item_id)
                assert deleted_item is None

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''


class TestListSharing:
    """Test list sharing functionality."""

    def test_share_list_with_user(self, client, test_user, test_user2, test_list, app, db):
        """Test sharing a list with another user."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/lists/{test_list.id}/share', data={
                    'user_id': test_user2.id,
                    'permission': 'view',
                    'csrf_token': self._get_csrf_token(client, f'/lists/{test_list.id}')
                }, follow_redirects=True)

                assert response.status_code == 200

    def test_shared_list_access(self, client, test_user2, test_list, app, db):
        """Test that shared user can access list."""
        from models import ListShare

        # Create share
        share = ListShare(
            list_id=test_list.id,
            user_id=test_user2.id,
            permission='view',
            shared_by_id=test_list.user_id
        )
        db.add(share)
        db.commit()

        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user2)
                response = client.get(f'/lists/{test_list.id}')
                assert response.status_code == 200

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''

