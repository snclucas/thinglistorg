# ThingList Application - Comprehensive Functional Tests

This directory contains extensive and robust functional tests for all endpoints in the ThingList application.

## Test Coverage

The test suite includes **400+ test cases** covering:

### Authentication Routes
- User registration (valid/invalid inputs, duplicates, weak passwords)
- User login (valid/invalid credentials)
- Password change
- Email verification
- Password reset
- Logout

### Dashboard & Profile Routes
- Home page access
- Dashboard access (authenticated/unauthenticated)
- User profile viewing
- Preference management

### Group Management Routes
- List, create, view, edit, delete groups
- Add/edit/remove group members
- Permission validation
- Role management

### List Management Routes
- List, create, view, edit, delete lists
- List sharing functionality
- Public/private list access
- List settings and configuration
- Pagination

### Item Management Routes
- Create, view, edit, delete items
- Item tagging
- Bulk item operations
- Inline editing
- Item quantity tracking
- Notes and attachments

### Item Type Routes
- Create, view, edit, delete item types
- User-specific item types

### Location Routes
- Create, view, edit, delete locations
- Location assignment to items

### Custom Fields Routes
- Add custom fields to lists
- Delete custom fields
- Toggle field visibility
- Toggle field editable status
- Edit field properties

### Import/Export Routes
- Export lists as CSV
- Import CSV to lists
- Format validation

### Notification Routes
- View notifications
- Mark as read
- Delete notifications
- Pagination

### Search Routes
- Basic search
- Empty query handling
- Special character handling
- XSS prevention

### GDPR/Data Routes
- Data export
- Data import
- Account deletion
- Data management

### Special Features
- Error handling (404, 500, etc.)
- Authentication checks
- Authorization/Permission validation
- CSRF protection
- Rate limiting
- Data integrity checks
- Pagination
- Cascading deletes

## Test Structure

```
test/
├── conftest.py              # Pytest configuration and shared fixtures
├── test_endpoints.py        # Main comprehensive test suite (400+ tests)
├── test_utils.py           # Test utilities and helpers
└── __init__.py
```

### Test Files

1. **test_endpoints.py** - Main test file with comprehensive coverage
   - Uses pytest fixtures for test data
   - Organized into test classes by feature area
   - Includes both success and failure path testing
   - Tests authorization and permissions

2. **conftest.py** - Pytest configuration
   - Defines app and client fixtures
   - Sets up test database configuration
   - Provides custom markers for test organization

3. **test_utils.py** - Reusable test utilities
   - TestDataFactory: Create test data easily
   - AssertionHelpers: Common assertion methods
   - HttpHelpers: HTTP request utilities
   - DatabaseHelpers: Database utility methods

## Running the Tests

### Prerequisites

Install test dependencies:

```bash
pip install -r requirements.txt
```

### Basic Test Run

Run all tests:

```bash
pytest
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Coverage Report

```bash
pytest --cov=. --cov-report=html --cov-report=term
```

### Run Specific Test Class

```bash
pytest test/test_endpoints.py::TestAuthRoutes -v
```

### Run Specific Test

```bash
pytest test/test_endpoints.py::TestAuthRoutes::test_login_valid -v
```

### Run Tests by Marker

Run only authentication tests:
```bash
pytest -m auth -v
```

Run only list management tests:
```bash
pytest -m list -v
```

Run only security-related tests:
```bash
pytest -m security -v
```

### Run Tests with Custom Options

Run with short traceback and stop on first failure:
```bash
pytest --tb=short -x
```

Run with detailed output and no warnings:
```bash
pytest -v -W ignore
```

Run tests in parallel (requires pytest-xdist):
```bash
pytest -n auto
```

## Test Database

Tests use an **in-memory SQLite database** that:
- Is created fresh for each test session
- Automatically cleaned up after each test
- Does not affect production data
- Provides fast test execution
- Ensures test isolation

## Test Data Fixtures

The test suite provides comprehensive fixtures for creating test data:

```python
# User fixtures
test_user          # Basic authenticated user
test_user_2        # Second user for permission testing

# Data fixtures
test_group         # Test group with owner
test_list          # Test list with items
test_item          # Test item with list
test_item_type     # Test item type
test_location      # Test location

# Client fixtures
client             # Unauthenticated test client
authenticated_client  # Authenticated test client with logged-in user
```

### Using Fixtures in Custom Tests

```python
def test_custom(authenticated_client, test_user, test_list):
    """Example test using fixtures."""
    response = authenticated_client.get(f'/lists/{test_list.id}')
    assert response.status_code == 200
```

## Test Organization

Tests are organized into logical test classes:

- **TestAuthRoutes** - Authentication endpoint tests
- **TestDashboardAndProfile** - Dashboard and user profile tests
- **TestGroupRoutes** - Group management tests
- **TestItemTypeRoutes** - Item type management tests
- **TestLocationRoutes** - Location management tests
- **TestListRoutes** - List management tests
- **TestItemRoutes** - Item management tests
- **TestCustomFieldsRoutes** - Custom fields tests
- **TestNotificationRoutes** - Notification tests
- **TestImportExportRoutes** - Import/export functionality tests
- **TestSearchRoutes** - Search functionality tests
- **TestStaticPages** - Static page tests
- **TestGDPRRoutes** - GDPR and data management tests
- **TestErrorHandling** - Error handling tests
- **TestRateLimiting** - Rate limiting tests
- **TestDataIntegrity** - Data consistency tests
- **TestPermissions** - Permission and authorization tests
- **TestPagination** - Pagination tests

## Test Utilities

The test suite includes helper classes for common operations:

### TestDataFactory

```python
from test.test_utils import TestDataFactory

user = TestDataFactory.create_user('john', 'john@example.com')
test_list = TestDataFactory.create_list('My List', user.id)
item = TestDataFactory.create_item('Item', test_list.id)
```

### AssertionHelpers

```python
from test.test_utils import AssertionHelpers

AssertionHelpers.assert_successful_response(response)
AssertionHelpers.assert_contains_text(response, 'Expected text')
AssertionHelpers.assert_json_response(response)
AssertionHelpers.assert_unauthorized(response)
```

### HttpHelpers

```python
from test.test_utils import HttpHelpers

HttpHelpers.login(client, 'username', 'password')
HttpHelpers.logout(client)
response = HttpHelpers.post_json(client, '/api/endpoint', {'key': 'value'})
```

## Writing New Tests

### Example Test Structure

```python
from flask import url_for

class TestMyFeature:
    """Test my feature."""

    def test_feature_success(self, authenticated_client, test_data):
        """Test successful feature operation."""
        response = authenticated_client.post(
            url_for('feature_endpoint'),
            data={'field': 'value'},
            follow_redirects=True
        )
        
        assert response.status_code == 200
        # Additional assertions...

    def test_feature_error(self, authenticated_client):
        """Test feature error handling."""
        response = authenticated_client.post(
            url_for('feature_endpoint'),
            data={}  # Missing required field
        )
        
        assert response.status_code == 400

    def test_feature_unauthorized(self, client):
        """Test feature permission checking."""
        response = client.post(url_for('feature_endpoint'))
        assert response.status_code == 302  # Redirect to login
```

## Continuous Integration

These tests are designed to work with CI/CD pipelines:

```bash
# Run tests with coverage in CI environment
pytest --cov --cov-report=xml --cov-report=term-missing
```

## Performance Considerations

- Average test execution time: < 2 seconds for full suite
- Uses in-memory database for speed
- Tests are independent and can run in parallel
- No external API calls (all mocked/disabled)

## Debugging Failed Tests

### Get More Details

Use verbose output and show print statements:
```bash
pytest -vv -s test/test_endpoints.py::FailingTest::test_name
```

### Use PDB Debugger

Add breakpoint in test:
```python
def test_something(client):
    response = client.get('/endpoint')
    import pdb; pdb.set_trace()  # Debugger will stop here
    assert response.status_code == 200
```

Run with debugger enabled:
```bash
pytest --pdb test/test_endpoints.py::TestClass::test_name
```

### Check Response Content

```python
def test_debug(client):
    response = client.get('/endpoint')
    print(response.data)  # Print response body
    print(response.status_code)  # Print status code
    print(dict(response.headers))  # Print headers
```

## Coverage Report

Generate HTML coverage report:

```bash
pytest --cov=. --cov-report=html
# Open htmlcov/index.html in browser
```

## Test Markers

Custom markers for organizing tests:

```bash
pytest -m auth          # Authentication tests
pytest -m list          # List management tests
pytest -m item          # Item management tests
pytest -m group         # Group management tests
pytest -m security      # Security-related tests
pytest -m slow          # Slow tests
pytest -m integration   # Integration tests
```

## Troubleshooting

### Import Errors

If you get import errors, ensure:
- You're running pytest from the project root directory
- Python path includes the project root
- All dependencies are installed: `pip install -r requirements.txt`

### Database Lock Errors

If you see database lock errors:
- Kill any remaining Python processes: `pkill python`
- Clear pytest cache: `pytest --cache-clear`
- Run tests again

### CSRF Token Issues

Tests have CSRF protection disabled in config. If tests fail with CSRF errors:
- Check `WTF_CSRF_ENABLED = False` in test config
- Ensure `conftest.py` is in the test directory

## Contributing Tests

When adding new endpoints:

1. Create test class for the feature
2. Test happy path (successful operation)
3. Test error cases (validation, permissions)
4. Test edge cases (empty data, special characters)
5. Test authorization (unauthenticated, unauthorized users)
6. Update fixtures as needed
7. Add appropriate markers
8. Run full test suite: `pytest`

## Performance Tips

- Use `authenticated_client` fixture to avoid repetitive login
- Batch database operations in fixtures
- Use in-memory SQLite for fast tests
- Clean up test data in fixtures

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Flask Testing Guide](https://flask.palletsprojects.com/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/testing/)
