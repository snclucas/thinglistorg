import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()


class Config:
    """Base configuration"""
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    if os.environ.get('FLASK_ENV') == 'production' and SECRET_KEY == 'dev-secret-key-change-in-production':
        raise ValueError('SECRET_KEY must be set in production environment!')

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No time limit for CSRF tokens
    WTF_CSRF_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_SSL_STRICT = False  # Disable SSL strict by default (override in production)
    WTF_CSRF_FIELD_NAME = 'csrf_token'  # Standard field name

    # Database
    # Build DATABASE_URL from components or use provided DATABASE_URL
    _db_host = os.environ.get('DB_HOST', 'localhost')
    _db_user = os.environ.get('DB_USER', '')
    _db_password = os.environ.get('DB_PASSWORD', '')
    _db_name = os.environ.get('DB_NAME', 'thinglistorg_db')
    _db_port = os.environ.get('DB_PORT', '3306')
    
    if os.environ.get('DATABASE_URL'):
        # Use full DATABASE_URL if provided
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    else:
        # Build from components
        SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'echo': False,
    }

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False  # Override in production
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'session'  # Simple name works in dev and prod
    SESSION_COOKIE_DOMAIN = None  # Use default domain

    # Security headers
    PREFERRED_URL_SCHEME = 'http'  # Default, override in production
    SESSION_REFRESH_EACH_REQUEST = True

    # Image upload configuration
    IMAGE_STORAGE_DIR = os.environ.get('IMAGE_STORAGE_DIR', os.path.join(os.getcwd(), 'image_uploads'))
    IMAGE_BASE_URL = os.environ.get('IMAGE_BASE_URL', '/image-content/')
    IMAGE_OUTPUT_FORMAT = os.environ.get('IMAGE_OUTPUT_FORMAT', 'webp')
    ITEM_IMAGE_DISPLAY_SIZE = int(os.environ.get('ITEM_IMAGE_DISPLAY_SIZE', '180'))
    IMAGE_MAX_SIZE = int(os.environ.get('IMAGE_MAX_SIZE', str(16 * 1024 * 1024)))
    IMAGE_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff'}

    # File upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_EXTENSIONS = {'csv', 'json', 'txt'}

    # Security: CORS and Content-Type
    JSON_SORT_KEYS = False
    JSON_COMPACT = True

    # reCAPTCHA Configuration (v2 - Checkbox)
    RECAPTCHA_ENABLED = os.environ.get('RECAPTCHA_ENABLED', 'false').lower() == 'true'
    RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC_KEY', '')
    RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE_KEY', '')

    # Registration Configuration
    REGISTRATIONS_ENABLED = os.environ.get('REGISTRATIONS_ENABLED', 'false').lower() == 'true'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False  # HTTP in development
    WTF_CSRF_SSL_STRICT = False  # Disable SSL strict in development


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False  # MUST be False in production
    TESTING = False
    SESSION_COOKIE_SECURE = True  # HTTPS only
    PREFERRED_URL_SCHEME = 'https'
    WTF_CSRF_SSL_STRICT = True  # Enforce SSL in production

    # Additional production security
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year cache for static files


class TestingConfig(Config):
    """Testing configuration - uses MySQL/MariaDB with test database"""
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False
    
    # Build test database URI from same credentials but with test database name
    _test_db_host = os.environ.get('DB_HOST_TEST', 'localhost')
    _test_db_user = os.environ.get('DB_USER_TEST', '')
    _test_db_password = os.environ.get('DB_PASSWORD_TEST', '')
    _test_db_port = os.environ.get('DB_PORT_TEST', '3306')
    _test_db_name = 'thinglistorg_test_db'  # Fixed test database name
    
    print("**************************************************************************************************************")

    if os.environ.get('DATABASE_URL'):
        # Strip database name from DATABASE_URL and replace with test database
        base_url = os.environ.get('DATABASE_URL').rsplit('/', 1)[0]
        SQLALCHEMY_DATABASE_URI = f'{base_url}/{_test_db_name}'
    else:
        # Build test database URI from same credentials as main config
        SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{_test_db_user}:{_test_db_password}@{_test_db_host}:{_test_db_port}/{_test_db_name}'
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'echo': False,
    }


# Config mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
