"""
Unit tests for forms and utility functions.
"""
import pytest
from forms import RegistrationForm, LoginForm, CreateGroupForm, AddGroupMemberForm
from models import User, db


class TestRegistrationForm:
    """Test RegistrationForm validation."""

    def test_valid_registration_form(self, app, db):
        """Test valid registration form."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'newuser',
                'email': 'new@example.com',
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert form.validate()

    def test_registration_username_too_short(self, app):
        """Test registration with username too short."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'ab',  # Too short
                'email': 'test@example.com',
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert not form.validate()
            assert 'username' in form.errors

    def test_registration_username_too_long(self, app):
        """Test registration with username too long."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'a' * 81,  # Too long
                'email': 'test@example.com',
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert not form.validate()
            assert 'username' in form.errors

    def test_registration_invalid_username_chars(self, app):
        """Test registration with invalid username characters."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'user@name',  # Invalid characters
                'email': 'test@example.com',
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert not form.validate()

    def test_registration_invalid_email(self, app):
        """Test registration with invalid email."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'newuser',
                'email': 'invalid-email',  # Invalid email
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert not form.validate()
            assert 'email' in form.errors

    def test_registration_password_too_short(self, app):
        """Test registration with password too short."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'newuser',
                'email': 'test@example.com',
                'password': 'short',  # Too short
                'password_confirm': 'short'
            })
            assert not form.validate()
            assert 'password' in form.errors

    def test_registration_password_mismatch(self, app):
        """Test registration with mismatched passwords."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'newuser',
                'email': 'test@example.com',
                'password': 'SecurePassword123',
                'password_confirm': 'DifferentPassword123'  # Doesn't match
            })
            assert not form.validate()
            assert 'password_confirm' in form.errors

    def test_registration_duplicate_username(self, app, test_user):
        """Test registration with duplicate username."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'testuser',  # Duplicate
                'email': 'different@example.com',
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert not form.validate()
            assert 'username' in form.errors

    def test_registration_duplicate_email(self, app, test_user):
        """Test registration with duplicate email."""
        with app.test_request_context():
            form = RegistrationForm(data={
                'username': 'newuser',
                'email': 'test@example.com',  # Duplicate
                'password': 'SecurePassword123',
                'password_confirm': 'SecurePassword123'
            })
            assert not form.validate()
            assert 'email' in form.errors


class TestLoginForm:
    """Test LoginForm validation."""

    def test_valid_login_form_username(self, app, test_user):
        """Test valid login form with username."""
        with app.test_request_context():
            form = LoginForm(data={
                'credential': 'testuser',
                'password': 'TestPassword123'
            })
            assert form.validate()

    def test_valid_login_form_email(self, app, test_user):
        """Test valid login form with email."""
        with app.test_request_context():
            form = LoginForm(data={
                'credential': 'test@example.com',
                'password': 'TestPassword123'
            })
            assert form.validate()

    def test_login_nonexistent_user(self, app):
        """Test login with non-existent user."""
        with app.test_request_context():
            form = LoginForm(data={
                'credential': 'nonexistent',
                'password': 'SomePassword123'
            })
            assert not form.validate()
            assert 'credential' in form.errors

    def test_login_invalid_password(self, app, test_user):
        """Test login with invalid password."""
        with app.test_request_context():
            form = LoginForm(data={
                'credential': 'testuser',
                'password': 'WrongPassword'
            })
            assert not form.validate()
            assert 'password' in form.errors

    def test_login_empty_credential(self, app):
        """Test login with empty credential."""
        with app.test_request_context():
            form = LoginForm(data={
                'credential': '',
                'password': 'SomePassword123'
            })
            assert not form.validate()
            assert 'credential' in form.errors

    def test_login_empty_password(self, app, test_user):
        """Test login with empty password."""
        with app.test_request_context():
            form = LoginForm(data={
                'credential': 'testuser',
                'password': ''
            })
            assert not form.validate()
            assert 'password' in form.errors


class TestCreateGroupForm:
    """Test CreateGroupForm validation."""

    def test_valid_create_group_form(self, app):
        """Test valid create group form."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': 'Test Group',
                'description': 'A test group',
                'allow_members_create_lists': True,
                'allow_members_edit_shared_lists': True
            })
            assert form.validate()

    def test_create_group_no_name(self, app):
        """Test create group without name."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': '',
                'description': 'Missing name',
                'allow_members_create_lists': True,
                'allow_members_edit_shared_lists': True
            })
            assert not form.validate()
            assert 'name' in form.errors

    def test_create_group_name_too_short(self, app):
        """Test create group with name too short."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': 'ab',  # Too short
                'description': 'Test',
                'allow_members_create_lists': True,
                'allow_members_edit_shared_lists': True
            })
            assert not form.validate()
            assert 'name' in form.errors

    def test_create_group_name_too_long(self, app):
        """Test create group with name too long."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': 'a' * 121,  # Too long
                'description': 'Test',
                'allow_members_create_lists': True,
                'allow_members_edit_shared_lists': True
            })
            assert not form.validate()
            assert 'name' in form.errors

    def test_create_group_description_too_long(self, app):
        """Test create group with description too long."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': 'Test Group',
                'description': 'a' * 1001,  # Too long
                'allow_members_create_lists': True,
                'allow_members_edit_shared_lists': True
            })
            assert not form.validate()
            assert 'description' in form.errors

    def test_create_group_optional_description(self, app):
        """Test create group with optional description."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': 'Test Group',
                'description': '',  # Empty is okay
                'allow_members_create_lists': True,
                'allow_members_edit_shared_lists': True
            })
            assert form.validate()

    def test_create_group_default_settings(self, app):
        """Test create group with default settings."""
        with app.test_request_context():
            form = CreateGroupForm(data={
                'name': 'Test Group'
            })
            # Form should still validate even without explicit boolean values
            assert form.validate()


class TestAddGroupMemberForm:
    """Test AddGroupMemberForm validation."""

    def test_valid_add_member_form(self, app, test_user2):
        """Test valid add member form."""
        with app.test_request_context():
            form = AddGroupMemberForm(data={
                'username': 'testuser2',
                'role': 'member'
            })
            assert form.validate()

    def test_add_member_no_username(self, app):
        """Test add member without username."""
        with app.test_request_context():
            form = AddGroupMemberForm(data={
                'username': '',
                'role': 'member'
            })
            assert not form.validate()
            assert 'username' in form.errors

    def test_add_member_username_too_short(self, app):
        """Test add member with username too short."""
        with app.test_request_context():
            form = AddGroupMemberForm(data={
                'username': 'ab',  # Too short
                'role': 'member'
            })
            assert not form.validate()
            assert 'username' in form.errors

    def test_add_member_valid_roles(self, app, test_user2):
        """Test add member with different valid roles."""
        with app.test_request_context():
            for role in ['member', 'admin', 'viewer']:
                form = AddGroupMemberForm(data={
                    'username': 'testuser2',
                    'role': role
                })
                assert form.validate()

    def test_add_member_invalid_role(self, app, test_user2):
        """Test add member with invalid role."""
        with app.test_request_context():
            form = AddGroupMemberForm(data={
                'username': 'testuser2',
                'role': 'invalid_role'
            })
            assert not form.validate()
            assert 'role' in form.errors


class TestUtilityFunctions:
    """Test utility functions and helpers."""

    def test_user_string_representation(self, test_user):
        """Test User __repr__ method."""
        assert repr(test_user) == '<User testuser>'

    def test_user_to_dict(self, test_user):
        """Test User to_dict method."""
        user_dict = test_user.to_dict()
        assert user_dict['username'] == 'testuser'
        assert user_dict['email'] == 'test@example.com'
        assert 'id' in user_dict
        assert 'created_at' in user_dict

    def test_user_get_items_per_page_string_conversion(self, test_user):
        """Test that items_per_page converts strings to integers."""
        test_user.set_items_per_page('50')
        assert test_user.get_items_per_page() == 50
        assert isinstance(test_user.get_items_per_page(), int)

    def test_password_hash_different_from_password(self, test_user):
        """Test that password hash is different from original."""
        password = 'TestPassword123'
        test_user.set_password(password)

        assert test_user.password_hash != password
        assert len(test_user.password_hash) > len(password)

    def test_datetime_fields_set(self, test_user):
        """Test that datetime fields are automatically set."""
        assert test_user.created_at is not None
        assert test_user.updated_at is not None
        assert isinstance(test_user.created_at, type(test_user.updated_at))

