"""
Pytest configuration and shared fixtures for ThingList tests.

This module provides:
- Pytest configuration
- Shared fixtures for all test modules
- Test database setup (MySQL/MariaDB test database)
- Application context management
"""

# IMPORTANT: Load .env FIRST, then set FLASK_ENV, then import config
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file FIRST (before setting Flask env)
load_dotenv()

# Set FLASK_ENV to 'testing' AFTER loading .env
os.environ['FLASK_ENV'] = 'testing'

import pytest

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import TestingConfig


@pytest.fixture(scope='session')
def app_config():
    """Return test configuration from TestingConfig.
    
    Uses MySQL/MariaDB test database configured in TestingConfig.
    Uses same DB credentials as production but connects to 'thinglistorg_test_db'.
    """
    return {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': TestingConfig.SQLALCHEMY_DATABASE_URI,
        'SQLALCHEMY_ENGINE_OPTIONS': TestingConfig.SQLALCHEMY_ENGINE_OPTIONS,
        'WTF_CSRF_ENABLED': False,
        'PRESERVE_CONTEXT_ON_EXCEPTION': False,
        'REGISTRATIONS_ENABLED': True,
        'RECAPTCHA_ENABLED': False,
        'SECRET_KEY': 'test-secret-key-12345',
        'UPLOAD_FOLDER': '/tmp/test_uploads',
        'IMAGE_STORAGE_DIR': '/tmp/test_images',
        'IMAGE_MAX_SIZE': 16 * 1024 * 1024,
        'IMAGE_ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif'},
        'SESSION_COOKIE_SECURE': False,
        'SESSION_COOKIE_HTTPONLY': True,
    }


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        'markers', 'integration: mark test as an integration test'
    )
    config.addinivalue_line(
        'markers', 'slow: mark test as slow running'
    )
    config.addinivalue_line(
        'markers', 'auth: mark test as related to authentication'
    )
    config.addinivalue_line(
        'markers', 'list: mark test as related to list management'
    )
    config.addinivalue_line(
        'markers', 'item: mark test as related to item management'
    )
    config.addinivalue_line(
        'markers', 'group: mark test as related to group management'
    )
    config.addinivalue_line(
        'markers', 'security: mark test as related to security'
    )
    config.addinivalue_line(
        'markers', 'performance: mark test as related to performance'
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to items based on their test module."""
    for item in items:
        # Add markers based on test class
        if 'Auth' in item.nodeid:
            item.add_marker(pytest.mark.auth)
        if 'List' in item.nodeid:
            item.add_marker(pytest.mark.list)
        if 'Item' in item.nodeid:
            item.add_marker(pytest.mark.item)
        if 'Group' in item.nodeid:
            item.add_marker(pytest.mark.group)
        if 'Permission' in item.nodeid or 'Error' in item.nodeid:
            item.add_marker(pytest.mark.security)


# Fixtures are imported from test_endpoints.py but can be extended here
