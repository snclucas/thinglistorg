"""
Pytest configuration and fixtures for the ThingList application.
"""
import pytest
import os
import sys

# Set testing environment BEFORE importing anything
os.environ['FLASK_ENV'] = 'testing'

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope='function')
def app():
    """Create Flask app with test config."""
    # Import after env is set
    from app import app as flask_app
    from app import db
    from config import TestingConfig

    # Configure for testing with in-memory SQLite
    flask_app.config.from_object(TestingConfig)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for tests

    # Create tables in test database
    with flask_app.app_context():
        # Drop and recreate all tables
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def db(app):
    """Database instance."""
    from app import db as database
    with app.app_context():
        yield database


@pytest.fixture
def test_user(app):
    """Create a test user."""
    from app import db
    from models import User

    with app.app_context():
        user = User(
            username='testuser',
            email='test@example.com',
            email_verified=True,
            is_active=True
        )
        user.set_password('TestPassword123')
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def test_user2(app):
    """Create a second test user."""
    from app import db
    from models import User

    with app.app_context():
        user = User(
            username='testuser2',
            email='test2@example.com',
            email_verified=True,
            is_active=True
        )
        user.set_password('TestPassword456')
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture
def test_list(app, test_user):
    """Create a test list."""
    from app import db
    from models import List

    with app.app_context():
        test_list = List(
            name='Test List',
            description='A test list',
            user_id=test_user.id,
            visibility='private'
        )
        db.session.add(test_list)
        db.session.commit()
        return test_list


@pytest.fixture
def test_item(app, test_list):
    """Create a test item."""
    from app import db
    from models import Item

    with app.app_context():
        item = Item(
            name='Test Item',
            description='A test item',
            quantity=5,
            list_id=test_list.id
        )
        db.session.add(item)
        db.session.commit()
        return item


@pytest.fixture
def test_group(app, test_user):
    """Create a test group."""
    from app import db
    from models import Group

    with app.app_context():
        group = Group(
            name='Test Group',
            description='A test group',
            owner_id=test_user.id
        )
        db.session.add(group)
        db.session.commit()
        return group


@pytest.fixture
def authenticated_client(client, test_user, app):
    """Test client with authenticated user."""
    with client:
        with app.app_context():
            from flask_login import login_user
            login_user(test_user)
            yield client


