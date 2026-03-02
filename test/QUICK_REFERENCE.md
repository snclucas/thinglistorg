"""
Quick reference guide for running ThingList tests.

This guide shows the most common test commands and their usage.
"""

## Quick Command Reference

### Basic Commands

# Run all tests
pytest

# Run all tests with verbose output
pytest -v

# Run all tests and stop on first failure
pytest -x

# Run tests with print statements visible
pytest -s


### Run Specific Tests

# Run a single test file
pytest test/test_endpoints.py

# Run a single test class
pytest test/test_endpoints.py::TestAuthRoutes

# Run a single test
pytest test/test_endpoints.py::TestAuthRoutes::test_login_valid

# Run tests matching a keyword
pytest -k "login"

# Run tests matching multiple keywords
pytest -k "login or register"


### Run by Feature Area

# Authentication tests only
pytest -m auth

# List management tests only
pytest -m list

# Item management tests only
pytest -m item

# Group management tests only
pytest -m group

# Security tests only
pytest -m security


### Coverage Reports

# Generate coverage report (HTML + terminal)
pytest --cov --cov-report=html --cov-report=term

# Generate terminal-only coverage report
pytest --cov --cov-report=term-missing

# Open HTML coverage report in browser
# On Windows:
start htmlcov/index.html
# On macOS:
open htmlcov/index.html
# On Linux:
xdg-open htmlcov/index.html


### Debugging and Troubleshooting

# Run with detailed output (more verbose)
pytest -vv

# Run with full tracebacks
pytest --tb=long

# Drop into Python debugger on failure
pytest --pdb

# Drop into debugger at start of test
pytest --pdbcls=IPython.terminal.debugger:TerminalPdb

# Show print statements and logging
pytest -s

# Show slowest tests
pytest --durations=10

# Run last failed tests only
pytest --lf

# Run failed tests first, then pass
pytest --ff


### Advanced Options

# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run with different Python versions (requires tox)
tox

# Generate JSON report
pytest --json-report

# Generate HTML report (requires pytest-html)
pytest --html=report.html

# Ignore warnings
pytest -W ignore

# Only run tests that haven't run recently
pytest -p no:cacheprovider


### Using the Test Runner Script

# Run all tests
python test/run_tests.py

# Run with coverage
python test/run_tests.py --coverage

# Run only auth tests
python test/run_tests.py --auth

# Run only list tests
python test/run_tests.py --list

# Run with verbosity and stop on first failure
python test/run_tests.py -x -vv

# Run last failed tests
python test/run_tests.py --lf

# Run in parallel
python test/run_tests.py --parallel


### Common Workflows

## Development Workflow

# 1. Run specific test you're working on
pytest test/test_endpoints.py::TestMyClass::test_my_feature -vv

# 2. Run all tests in that file
pytest test/test_endpoints.py -v

# 3. Run all tests
pytest


## Pre-commit Workflow

# Run tests with coverage
pytest --cov --cov-report=term-missing

# Run with specific verbosity
pytest -v


## CI/CD Pipeline

# Run all tests with coverage and exit on failure
pytest --cov --cov-report=xml -x

# Run with HTML report
pytest --html=report.html --self-contained-html


## Debugging a Failing Test

# 1. Run the specific test with verbose output
pytest test/test_endpoints.py::FailingTest::test_name -vv

# 2. Show print statements
pytest test/test_endpoints.py::FailingTest::test_name -s

# 3. Drop into debugger
pytest test/test_endpoints.py::FailingTest::test_name --pdb

# 4. Show full traceback
pytest test/test_endpoints.py::FailingTest::test_name --tb=long


## Performance Optimization

# Run tests in parallel
pytest -n auto

# Show slowest 20 tests
pytest --durations=20

# Profile test execution
pytest --durations=0


## Test Organization Commands

# List all test items (don't run)
pytest --collect-only

# List all tests with their markers
pytest --collect-only -q

# List all available markers
pytest --markers


## Useful pytest Plugins

# Install common useful plugins:
pip install pytest-cov        # Coverage reports
pip install pytest-html       # HTML reports
pip install pytest-xdist      # Parallel execution
pip install pytest-timeout    # Timeout support
pip install pytest-mock       # Mocking support
pip install pytest-flask      # Flask testing

# Then use them:
pytest --cov --html=report.html -n auto --durations=10


## Environment Variables

# Run in test mode (set before running pytest)
# Windows:
set FLASK_ENV=testing
pytest

# macOS/Linux:
FLASK_ENV=testing pytest


## Common Pytest Options Explained

-v              Verbose output
-vv             Very verbose output
-x              Stop on first failure
-s              Show print statements
-k EXPRESSION   Run tests matching expression
-m MARKER       Run tests with marker
--lf            Run last failed
--ff            Run failed first
--tb=FORMAT     Traceback format (short, long, native, no, line)
--pdb           Start debugger on failure
--durations=N   Show N slowest tests
-n NUM          Run N tests in parallel (with pytest-xdist)
--cov           Generate coverage report
--html          Generate HTML report


## Troubleshooting Tips

# If tests hang:
Ctrl+C to interrupt, then:
pytest -x -vv test/test_endpoints.py::TestName::test_name

# If you get import errors:
# Make sure you're in the project root directory
cd /path/to/thinglistorg
pytest

# If database is locked:
pkill python
pytest --cache-clear
pytest

# If fixtures not found:
# Make sure conftest.py is in the test directory
# Check that fixtures are defined in conftest.py or test file


## Useful Pytest Configurations

# .pytest.ini or pytest.ini in project root
[pytest]
python_files = test_*.py
python_classes = Test*
python_functions = test_*
testpaths = test
addopts = -v --strict-markers --tb=short
markers =
    auth: Authentication tests
    list: List management tests
    item: Item management tests


"""
