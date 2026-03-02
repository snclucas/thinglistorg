# Testing Configuration Fix - Verification Guide

## What Was Fixed

1. **config.py** - Removed `sys.exit()` call from TestingConfig class that was blocking initialization
2. **config.py** - Updated TestingConfig to use same credentials as production (DB_HOST, DB_USER, DB_PASSWORD, DB_PORT) but with fixed test database name `thinglistorg_test_db`
3. **test/conftest.py** - Set `FLASK_ENV='testing'` at the very top (before importing anything) so the app loads with TestingConfig
4. **test/test_endpoints.py** - Set `FLASK_ENV='testing'` early and simplified the app fixture to rely on config instead of manual overrides

## How It Works Now

1. **conftest.py** sets `FLASK_ENV='testing'` at module load time
2. **test_endpoints.py** also sets `FLASK_ENV='testing'` early to ensure it's set
3. When the Flask app is imported in the fixture, it reads `FLASK_ENV='testing'` and loads **TestingConfig** from `config.py`
4. **TestingConfig** is configured to use MySQL/MariaDB with the test database `thinglistorg_test_db`
5. The database uses the same credentials as your configured environment (DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

## Verification

Run this command to verify the test configuration is working:

```bash
# Set your database credentials first (Windows)
set DB_HOST=localhost
set DB_USER=root
set DB_PASSWORD=yourpassword
set DB_PORT=3306

# On macOS/Linux use 'export' instead of 'set'

# Run pytest with verbose output to see which config is loaded
pytest -v -s test/test_endpoints.py::TestAuthRoutes::test_login_valid
```

You should see in the output no errors about SQLite, and instead see MySQL connection attempts.

## Check Test Database Is Being Used

Before running tests, verify the test database exists:

```bash
# Check if test database exists
mysql -u root -p -e "USE thinglistorg_test_db; SELECT 'Test database exists';"

# If it doesn't exist, create it:
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS thinglistorg_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

## Environment Variable Checklist

Make sure these are set in your environment:

```bash
# Windows - set these in PowerShell or Command Prompt
set DB_HOST=your_host
set DB_USER=your_user
set DB_PASSWORD=your_password
set DB_PORT=3306

# macOS/Linux - set these in your shell
export DB_HOST=your_host
export DB_USER=your_user
export DB_PASSWORD=your_password
export DB_PORT=3306
```

## Troubleshooting

### Error: "Access denied for user"
- Check DB_USER and DB_PASSWORD are correct
- Verify MySQL user has permissions on `thinglistorg_test_db`

### Error: "Unknown database 'thinglistorg_test_db'"
- Create the test database first (see above)

### Still not using test config
- Verify conftest.py is in the test directory
- Verify `os.environ['FLASK_ENV'] = 'testing'` is at the very top
- Run: `python -c "import sys; sys.path.insert(0, '.'); from test import conftest; print(conftest)"`

## Files Changed

1. **config.py** - Fixed TestingConfig (removed sys.exit, corrected credentials)
2. **test/conftest.py** - Added FLASK_ENV='testing' at top, fixed imports
3. **test/test_endpoints.py** - Added FLASK_ENV='testing' early, simplified app fixture

## Running Tests

```bash
# Simple run
pytest

# With verbose output
pytest -v

# With coverage
pytest --cov --cov-report=term-missing

# Specific test
pytest test/test_endpoints.py::TestAuthRoutes::test_login_valid -v
```

The tests should now properly use your MySQL/MariaDB test database configuration!
