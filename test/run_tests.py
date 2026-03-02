#!/usr/bin/env python
"""
Test Runner Script for ThingList Application

Provides convenient commands for running tests with various options.
Usage: python run_tests.py [options] [test_path]

Examples:
    python run_tests.py                  # Run all tests
    python run_tests.py -v              # Verbose output
    python run_tests.py --coverage      # With coverage report
    python run_tests.py auth            # Run only auth tests
    python run_tests.py -x              # Stop on first failure
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd):
    """Run a shell command and return the exit code."""
    print(f"Running: {' '.join(cmd)}\n")
    return subprocess.call(cmd)


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(
        description='ThingList Test Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                        # Run all tests
  %(prog)s -v                     # Verbose output
  %(prog)s --coverage             # Generate coverage report
  %(prog)s auth                   # Run only auth tests
  %(prog)s test_endpoints.py      # Run specific test file
  %(prog)s TestAuthRoutes         # Run specific test class
  %(prog)s test_endpoints.py::TestAuthRoutes::test_login_valid  # Run specific test
  %(prog)s -k "login"             # Run tests matching keyword
  %(prog)s -m auth                # Run tests with marker
  %(prog)s -x                     # Stop on first failure
  %(prog)s --lf                   # Run last failed tests
        ''')
    
    # Main arguments
    parser.add_argument(
        'test_path',
        nargs='?',
        default='test',
        help='Test path or test name (default: test)'
    )
    
    # Output options
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=1,
        help='Increase verbosity (use -vv for more details)'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Minimize output'
    )
    
    # Test selection
    parser.add_argument(
        '-k', '--keyword',
        help='Only run tests matching keyword'
    )
    
    parser.add_argument(
        '-m', '--marker',
        help='Only run tests with marker'
    )
    
    parser.add_argument(
        '--auth',
        action='store_true',
        help='Run only authentication tests'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='Run only list management tests'
    )
    
    parser.add_argument(
        '--item',
        action='store_true',
        help='Run only item management tests'
    )
    
    parser.add_argument(
        '--group',
        action='store_true',
        help='Run only group management tests'
    )
    
    parser.add_argument(
        '--security',
        action='store_true',
        help='Run only security tests'
    )
    
    # Execution options
    parser.add_argument(
        '-x', '--exit-on-first',
        action='store_true',
        help='Exit on first failure'
    )
    
    parser.add_argument(
        '--lf', '--last-failed',
        action='store_true',
        dest='last_failed',
        help='Run only last failed tests'
    )
    
    parser.add_argument(
        '--ff', '--failed-first',
        action='store_true',
        dest='failed_first',
        help='Run failed tests first'
    )
    
    parser.add_argument(
        '-p', '--parallel',
        action='store_true',
        help='Run tests in parallel (requires pytest-xdist)'
    )
    
    # Report options
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Run with coverage report (HTML and terminal)'
    )
    
    parser.add_argument(
        '--cov-only',
        action='store_true',
        help='Show only coverage summary'
    )
    
    parser.add_argument(
        '--html',
        action='store_true',
        help='Generate HTML report (requires pytest-html)'
    )
    
    parser.add_argument(
        '--tb',
        default='short',
        choices=['short', 'long', 'native', 'no', 'line'],
        help='Traceback format'
    )
    
    # Other options
    parser.add_argument(
        '-s', '--show-output',
        action='store_true',
        help='Show print statements and logging'
    )
    
    parser.add_argument(
        '--pdb',
        action='store_true',
        help='Start debugger on failures'
    )
    
    parser.add_argument(
        '--profile',
        action='store_true',
        help='Profile test execution time'
    )
    
    parser.add_argument(
        '--random',
        action='store_true',
        help='Run tests in random order'
    )
    
    parser.add_argument(
        '--durations',
        type=int,
        metavar='N',
        help='Show N slowest tests'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Build pytest command
    cmd = ['pytest']
    
    # Add test path
    test_path = args.test_path
    if test_path.startswith('Test'):
        # If it's a test class, search in test_endpoints.py
        test_path = f'test/test_endpoints.py::{test_path}'
    elif ':' not in test_path and not test_path.endswith('.py'):
        # If it's just a name, try to find it
        if not test_path.startswith('test'):
            test_path = f'test -{k} {test_path}' if args.keyword else f'test -k {test_path}'
    
    if not test_path.startswith('-'):
        cmd.append(test_path)
    
    # Add verbosity
    if args.quiet:
        cmd.append('-q')
    else:
        cmd.append('-' + 'v' * args.verbose)
    
    # Add test selection options
    if args.keyword:
        cmd.extend(['-k', args.keyword])
    
    if args.marker:
        cmd.extend(['-m', args.marker])
    elif args.auth:
        cmd.extend(['-m', 'auth'])
    elif args.list:
        cmd.extend(['-m', 'list'])
    elif args.item:
        cmd.extend(['-m', 'item'])
    elif args.group:
        cmd.extend(['-m', 'group'])
    elif args.security:
        cmd.extend(['-m', 'security'])
    
    # Add execution options
    if args.exit_on_first:
        cmd.append('-x')
    
    if args.last_failed:
        cmd.append('--lf')
    
    if args.failed_first:
        cmd.append('--ff')
    
    if args.parallel:
        cmd.extend(['-n', 'auto'])
    
    # Add report options
    if args.coverage:
        cmd.extend([
            '--cov=.',
            '--cov-report=html',
            '--cov-report=term-missing'
        ])
    elif args.cov_only:
        cmd.extend([
            '--cov=.',
            '--cov-report=term'
        ])
    
    if args.html:
        cmd.append('--html=report.html')
    
    # Add traceback format
    cmd.append(f'--tb={args.tb}')
    
    # Add other options
    if args.show_output:
        cmd.append('-s')
    
    if args.pdb:
        cmd.append('--pdb')
    
    if args.profile:
        cmd.extend(['--durations=10'])
    elif args.durations:
        cmd.extend([f'--durations={args.durations}'])
    
    if args.random:
        cmd.append('-p')
        cmd.append('no:randomly')  # This typically requires pytest-randomly
    
    # Run pytest
    exit_code = run_command(cmd)
    
    # Print results
    if exit_code == 0:
        print('\n' + '='*60)
        print('✓ All tests passed!')
        print('='*60)
        
        if args.coverage:
            print('\nCoverage report generated in htmlcov/index.html')
        if args.html:
            print('\nTest report generated in report.html')
    else:
        print('\n' + '='*60)
        print('✗ Tests failed')
        print('='*60)
        
        if not args.last_failed:
            print('\nRun again with --lf to test only failed tests')
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
