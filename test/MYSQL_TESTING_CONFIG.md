# MySQL/MariaDB Testing Configuration

## Overview

The ThingList application tests now use **MySQL/MariaDB** for testing instead of SQLite in-memory databases.

## Configuration Details

### Test Database Name
- **Database**: `thinglistorg_test_db`
- This is a fixed database name used exclusively for testing
- It does NOT affect your production database

### Database Credentials
The test database uses the **same credentials** as configured for your development/production environment:

- **Host**: `DB_HOST` environment variable (default: `localhost`)
- **User**: `DB_USER` environment variable
- **Password**: `DB_PASSWORD` environment variable  
- **Port**: `DB_PORT` environment variable (default: `3306`)

### Configuration Files

#### 1. `config.py` - TestingConfig Class
```python
class TestingConfig(Config):
    """Testing configuration - uses MySQL/MariaDB with test database"""
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{user}:{password}@{host}:{port}/thinglistorg_test_db'
```

#### 2. `test/conftest.py` - Pytest Fixture Configuration
```python
@pytest.fixture(scope='session')
def app_config():
    """Return test configuration from TestingConfig."""
    return {
        'SQLALCHEMY_DATABASE_URI': TestingConfig.SQLALCHEMY_DATABASE_URI,
        # ... other config
    }
```

#### 3. `test/test_endpoints.py` - Test App Fixture
```python
@pytest.fixture(scope='function')
def app():
    """Create and configure a test Flask app instance."""
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = TestingConfig.SQLALCHEMY_DATABASE_URI
    # ... app setup
```

## Setup Instructions

### Prerequisites

1. **MySQL/MariaDB server running** on your configured host and port
2. **Environment variables set** for database credentials:
   ```bash
   # Set your database credentials
   set DB_HOST=localhost          # Windows
   set DB_USER=root               # or your MySQL user
   set DB_PASSWORD=yourpassword   # or your MySQL password
   set DB_PORT=3306               # Default MySQL port
   
   # Or on macOS/Linux:
   export DB_HOST=localhost
   export DB_USER=root
   export DB_PASSWORD=yourpassword
   export DB_PORT=3306
   ```

### Create Test Database

The test database needs to exist before running tests:

```sql
-- Connect to MySQL/MariaDB
mysql -h localhost -u root -p

-- Create test database
CREATE DATABASE IF NOT EXISTS thinglistorg_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Verify
SHOW DATABASES LIKE 'thinglistorg_test%';
```

Or using the command line:

```bash
# Windows (with MySQL in PATH)
mysql -h localhost -u root -p -e "CREATE DATABASE IF NOT EXISTS thinglistorg_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# macOS/Linux
mysql -h localhost -u root -p -e "CREATE DATABASE IF NOT EXISTS thinglistorg_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with specific test file
pytest test/test_endpoints.py -v

# Run specific test class
pytest test/test_endpoints.py::TestAuthRoutes -v
```

### With Coverage Report

```bash
# Generate HTML and terminal coverage report
pytest --cov --cov-report=html --cov-report=term-missing

# Open coverage report in browser
# Windows:
start htmlcov/index.html
# macOS:
open htmlcov/index.html
# Linux:
xdg-open htmlcov/index.html
```

### Using Test Runner Script

```bash
python test/run_tests.py                 # All tests
python test/run_tests.py --coverage      # With coverage
python test/run_tests.py -vv            # Verbose output
python test/run_tests.py --auth         # Auth tests only
python test/run_tests.py --lf           # Last failed tests
```

## Troubleshooting

### Database Connection Error

If you get a connection error:

1. **Verify MySQL is running**:
   ```bash
   # Windows
   mysql -u root -p -e "SELECT 1"
   
   # macOS/Linux
   mysql -u root -p -e "SELECT 1"
   ```

2. **Verify credentials** in environment variables:
   ```bash
   # Windows
   echo %DB_HOST%
   echo %DB_USER%
   echo %DB_PORT%
   
   # macOS/Linux
   echo $DB_HOST
   echo $DB_USER
   echo $DB_PORT
   ```

3. **Verify test database exists**:
   ```bash
   mysql -u root -p -e "USE thinglistorg_test_db; SELECT 1;"
   ```

### "No such table" Error

If you get table not found errors, the database tables need to be created. The tests should do this automatically via `db.create_all()`, but you can manually create them:

```bash
# Run the admin setup script (if available)
python admin/init_database.py

# Or use Flask shell
flask shell
# Then in the Flask shell:
>>> from models import db
>>> db.create_all()
>>> exit()
```

### Permissions Error

If you get permission errors when creating tables:

1. Verify the MySQL user has proper permissions:
   ```sql
   GRANT ALL PRIVILEGES ON thinglistorg_test_db.* TO 'your_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. Or create the database with the correct user directly:
   ```bash
   mysql -u your_user -p -e "CREATE DATABASE thinglistorg_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
   ```

### Test Database Cleanup

The test database accumulates data between test runs. To clean it up:

```bash
# Option 1: Drop and recreate (cleanest)
mysql -u root -p -e "DROP DATABASE thinglistorg_test_db; CREATE DATABASE thinglistorg_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# Option 2: Truncate all tables (if database already exists)
# Run this Python script:

from config import TestingConfig
from models import db
from app import app

app.config.from_object(TestingConfig)
with app.app_context():
    # Drop all and recreate fresh
    db.drop_all()
    db.create_all()
```

## Differences from SQLite Testing

### Advantages of MySQL Testing
- ✅ Tests production-like environment (same database engine)
- ✅ Catches database-specific issues early
- ✅ Better for testing performance
- ✅ Can share test database with multiple developers/CI pipelines
- ✅ Tests connection pooling and real database operations

### Considerations
- ⚠️ Tests require MySQL/MariaDB to be running
- ⚠️ Tests are slightly slower than in-memory SQLite
- ⚠️ Requires database cleanup between test runs (automatic in code, but can accumulate)
- ⚠️ Requires proper MySQL credentials configured

## Configuration via Environment Variables

You can also use a full DATABASE_URL:

```bash
# Windows
set DATABASE_URL=mysql+pymysql://root:password@localhost:3306/thinglistorg_dev

# macOS/Linux
export DATABASE_URL=mysql+pymysql://root:password@localhost:3306/thinglistorg_dev
```

## CI/CD Integration

For automated testing in CI/CD pipelines (GitHub Actions, GitLab CI, etc.):

1. Install MySQL service in CI environment
2. Set environment variables in pipeline
3. Run database initialization before tests
4. Tests will use the configured test database

Example for GitHub Actions:

```yaml
services:
  mysql:
    image: mysql:8.0
    options: --health-cmd="mysqladmin ping" --health-interval=10s --health-timeout=5s --health-retries=3
    env:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: thinglistorg_test_db

env:
  DB_HOST: localhost
  DB_USER: root
  DB_PASSWORD: password
  DB_PORT: 3306
```

## Reverting to SQLite (If Needed)

To revert to SQLite in-memory testing:

1. In `config.py`, update TestingConfig:
```python
class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': 'sqlalchemy.pool.StaticPool',
    }
```

2. In `test/conftest.py`, revert the app_config fixture:
```python
@pytest.fixture(scope='session')
def app_config():
    return {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        # ... rest of config
    }
```

3. In `test/test_endpoints.py`, revert the app fixture:
```python
@pytest.fixture(scope='function')
def app():
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    # ... rest of app setup
```

## Summary

Your tests are now configured to use:
- **Database Engine**: MySQL/MariaDB (same as production)
- **Test Database**: `thinglistorg_test_db` (isolated from production)
- **Credentials**: Same as your environment configuration
- **Automatic Setup**: Tables are created/dropped automatically by test fixtures
- **Full Integration**: Tests run against real database engine, not mocked

This provides a more realistic testing environment that better reflects production behavior.
