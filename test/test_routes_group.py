"""
Functional tests for group management routes.
"""
import pytest
from models import Group, GroupMember, db


class TestGroupRoutes:
    """Test group management routes."""

    def test_groups_page_requires_auth(self, client):
        """Test that groups page requires authentication."""
        response = client.get('/groups', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_groups_page_authenticated(self, client, test_user, test_group, app):
        """Test groups page with authenticated user."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/groups')
                assert response.status_code == 200

    def test_create_group_page_loads(self, client, test_user, app):
        """Test create group page loads."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/groups/create')
                assert response.status_code == 200
                assert b'Create' in response.data or b'Group' in response.data

    def test_create_group_valid(self, client, test_user, app, db):
        """Test creating a valid group."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post('/groups/create', data={
                    'name': 'New Group',
                    'description': 'A test group',
                    'allow_members_create_lists': True,
                    'allow_members_edit_shared_lists': True,
                    'csrf_token': self._get_csrf_token(client, '/groups/create')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify group was created
                new_group = Group.query.filter_by(name='New Group').first()
                assert new_group is not None
                assert new_group.owner_id == test_user.id

    def test_create_group_without_name(self, client, test_user, app):
        """Test creating group without name."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post('/groups/create', data={
                    'name': '',
                    'description': 'Missing name',
                    'csrf_token': self._get_csrf_token(client, '/groups/create')
                }, follow_redirects=True)

                assert response.status_code == 200
                assert b'Error' in response.data or b'required' in response.data

    def test_view_group_as_owner(self, client, test_user, test_group, app):
        """Test viewing group as owner."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get(f'/groups/{test_group.id}')
                assert response.status_code == 200
                assert test_group.name.encode() in response.data

    def test_edit_group_as_owner(self, client, test_user, test_group, app, db):
        """Test editing group as owner."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/groups/{test_group.id}/edit', data={
                    'name': 'Updated Group Name',
                    'description': 'Updated description',
                    'allow_members_create_lists': False,
                    'allow_members_edit_shared_lists': True,
                    'csrf_token': self._get_csrf_token(client, f'/groups/{test_group.id}/edit')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify group was updated
                updated_group = Group.query.get(test_group.id)
                assert updated_group.name == 'Updated Group Name'

    def test_delete_group_as_owner(self, client, test_user, test_group, app, db):
        """Test deleting group as owner."""
        group_id = test_group.id

        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/groups/{group_id}/delete', data={
                    'csrf_token': self._get_csrf_token(client, f'/groups/{group_id}')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify group was deleted
                deleted_group = Group.query.get(group_id)
                assert deleted_group is None

    def test_non_owner_cannot_edit_group(self, client, test_user2, test_group, app):
        """Test that non-owner cannot edit group."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user2)
                response = client.post(f'/groups/{test_group.id}/edit', data={
                    'name': 'Hacked Group Name',
                    'description': 'Hacked',
                    'csrf_token': self._get_csrf_token(client, f'/groups/{test_group.id}')
                }, follow_redirects=True)

                assert response.status_code == 200
                assert b'permission' in response.data.lower() or b'Error' in response.data

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''


class TestGroupMembership:
    """Test group membership functionality."""

    def test_add_member_to_group(self, client, test_user, test_user2, test_group, app, db):
        """Test adding a member to a group."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/groups/{test_group.id}/members/add', data={
                    'username': 'testuser2',
                    'role': 'member',
                    'csrf_token': self._get_csrf_token(client, f'/groups/{test_group.id}')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify member was added
                member = GroupMember.query.filter_by(
                    group_id=test_group.id,
                    user_id=test_user2.id
                ).first()
                assert member is not None
                assert member.role == 'member'

    def test_member_can_access_group_lists(self, client, test_user2, test_group, app, db):
        """Test that group members can access group lists."""
        # Add user2 as member
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user2)
                response = client.get(f'/groups/{test_group.id}')
                assert response.status_code == 200

    def test_remove_member_from_group(self, client, test_user, test_user2, test_group, app, db):
        """Test removing a member from a group."""
        # Add member first
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.post(f'/groups/{test_group.id}/members/{test_user2.id}/remove', data={
                    'csrf_token': self._get_csrf_token(client, f'/groups/{test_group.id}')
                }, follow_redirects=True)

                assert response.status_code == 200

                # Verify member was removed
                removed_member = GroupMember.query.filter_by(
                    group_id=test_group.id,
                    user_id=test_user2.id
                ).first()
                assert removed_member is None

    def test_viewer_role_restrictions(self, client, test_user2, test_group, app, db):
        """Test that viewer role has restricted permissions."""
        # Add user2 as viewer
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='viewer'
        )
        db.add(member)
        db.commit()

        # Verify viewer can view but not edit
        assert member.can_view() is True
        assert member.can_edit() is False
        assert member.can_manage() is False

    def test_admin_role_permissions(self, client, test_user2, test_group, app, db):
        """Test that admin role has full permissions."""
        # Add user2 as admin
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='admin'
        )
        db.add(member)
        db.commit()

        # Verify admin can do everything
        assert member.can_view() is True
        assert member.can_edit() is True
        assert member.can_manage() is True

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''

