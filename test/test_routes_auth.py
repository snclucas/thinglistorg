"""
Functional tests for authentication routes.
"""
import pytest
from urllib.parse import urlparse, parse_qs
from models import User, db


class TestRegistrationRoute:
    """Test user registration route."""

    def test_register_page_loads(self, client):
        """Test registration page loads successfully."""
        response = client.get('/register')
        assert response.status_code == 200
        assert b'Register' in response.data

    def test_register_valid_user(self, client, db):
        """Test registering a valid user."""
        response = client.post('/register', data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'SecurePass123',
            'password_confirm': 'SecurePass123',
            'csrf_token': self._get_csrf_token(client, '/register')
        }, follow_redirects=True)

        assert response.status_code == 200

        # Check user was created
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.email == 'new@example.com'

    def test_register_password_mismatch(self, client):
        """Test registration with mismatched passwords."""
        response = client.post('/register', data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'SecurePass123',
            'password_confirm': 'DifferentPass123',
            'csrf_token': self._get_csrf_token(client, '/register')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Passwords must match' in response.data or b'Error' in response.data

    def test_register_short_password(self, client):
        """Test registration with short password."""
        response = client.post('/register', data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'short',
            'password_confirm': 'short',
            'csrf_token': self._get_csrf_token(client, '/register')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'at least 8 characters' in response.data or b'Error' in response.data

    def test_register_invalid_username_format(self, client):
        """Test registration with invalid username format."""
        response = client.post('/register', data={
            'username': 'user@name!',  # Invalid characters
            'email': 'new@example.com',
            'password': 'SecurePass123',
            'password_confirm': 'SecurePass123',
            'csrf_token': self._get_csrf_token(client, '/register')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Error' in response.data or b'letters, numbers' in response.data

    def test_register_duplicate_username(self, client, test_user):
        """Test registration with existing username."""
        response = client.post('/register', data={
            'username': 'testuser',  # Existing username
            'email': 'different@example.com',
            'password': 'SecurePass123',
            'password_confirm': 'SecurePass123',
            'csrf_token': self._get_csrf_token(client, '/register')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'already taken' in response.data or b'Error' in response.data

    def test_register_duplicate_email(self, client, test_user):
        """Test registration with existing email."""
        response = client.post('/register', data={
            'username': 'newuser',
            'email': 'test@example.com',  # Existing email
            'password': 'SecurePass123',
            'password_confirm': 'SecurePass123',
            'csrf_token': self._get_csrf_token(client, '/register')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'already registered' in response.data or b'Error' in response.data

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        # Extract CSRF token from form (simple regex approach)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''


class TestLoginRoute:
    """Test user login route."""

    def test_login_page_loads(self, client):
        """Test login page loads successfully."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Login' in response.data or b'Username or Email' in response.data

    def test_login_valid_credentials_with_username(self, client, test_user):
        """Test login with valid username."""
        response = client.post('/login', data={
            'credential': 'testuser',
            'password': 'TestPassword123',
            'csrf_token': self._get_csrf_token(client, '/login')
        }, follow_redirects=True)

        assert response.status_code == 200
        # Should redirect to dashboard for authenticated user
        assert b'Dashboard' in response.data or b'logout' in response.data.lower()

    def test_login_valid_credentials_with_email(self, client, test_user):
        """Test login with valid email."""
        response = client.post('/login', data={
            'credential': 'test@example.com',
            'password': 'TestPassword123',
            'csrf_token': self._get_csrf_token(client, '/login')
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_login_invalid_password(self, client, test_user):
        """Test login with invalid password."""
        response = client.post('/login', data={
            'credential': 'testuser',
            'password': 'WrongPassword',
            'csrf_token': self._get_csrf_token(client, '/login')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Invalid password' in response.data or b'Error' in response.data

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post('/login', data={
            'credential': 'nonexistent',
            'password': 'SomePassword123',
            'csrf_token': self._get_csrf_token(client, '/login')
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'not found' in response.data or b'Error' in response.data

    @staticmethod
    def _get_csrf_token(client, url):
        """Helper to extract CSRF token from form."""
        response = client.get(url)
        import re
        match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', response.get_data(as_text=True))
        return match.group(1) if match else ''


class TestDashboardRoute:
    """Test dashboard route."""

    def test_dashboard_requires_authentication(self, client):
        """Test that dashboard requires authentication."""
        response = client.get('/dashboard', follow_redirects=True)
        assert response.status_code == 200
        # Should be redirected to login
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_dashboard_authenticated_user(self, client, test_user, app):
        """Test dashboard with authenticated user."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/dashboard')
                assert response.status_code == 200
                assert b'Dashboard' in response.data or b'Groups' in response.data

    def test_dashboard_displays_user_content(self, client, test_user, test_list, app):
        """Test that dashboard displays user's lists and groups."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/dashboard')
                assert response.status_code == 200


class TestLogoutRoute:
    """Test logout route."""

    def test_logout_requires_authentication(self, client):
        """Test that logout requires authentication."""
        response = client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
        # Should redirect to login
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_logout_authenticated_user(self, client, test_user, app):
        """Test logging out an authenticated user."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/logout', follow_redirects=True)
                assert response.status_code == 200
                # After logout, should not see dashboard
                response = client.get('/dashboard', follow_redirects=True)
                assert b'Login' in response.data or b'log in' in response.data.lower()


class TestProfileRoute:
    """Test profile route."""

    def test_profile_requires_authentication(self, client):
        """Test that profile requires authentication."""
        response = client.get('/profile', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data or b'log in' in response.data.lower()

    def test_profile_authenticated_user(self, client, test_user, app):
        """Test profile page for authenticated user."""
        with app.test_request_context():
            from flask_login import login_user
            with client:
                login_user(test_user)
                response = client.get('/profile')
                assert response.status_code == 200
                assert b'testuser' in response.data or b'Profile' in response.data

