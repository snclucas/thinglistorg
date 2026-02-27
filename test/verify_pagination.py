#!/usr/bin/env python
"""
Verify pagination implementation for ThingList

This script checks:
1. User model has preferences field
2. User methods for pagination work
3. Database migrations applied
4. Routes accessible
"""

from app import app, db
from models import User

def verify_user_model():
    """Verify User model has pagination support."""
    print("=" * 60)
    print("Verifying User Model")
    print("=" * 60)

    with app.app_context():
        # Check if preferences field exists
        user = User.query.first()
        if user:
            print(f"✓ Found test user: {user.username}")

            # Test get_items_per_page
            per_page = user.get_items_per_page()
            print(f"✓ get_items_per_page() returns: {per_page}")
            assert isinstance(per_page, int), "per_page should be int"
            assert 5 <= per_page <= 100, "per_page should be between 5-100"

            # Test set_items_per_page
            user.set_items_per_page(50)
            db.session.commit()
            per_page = user.get_items_per_page()
            print(f"✓ set_items_per_page(50) successful, verified: {per_page}")
            assert per_page == 50, "per_page should be 50 after setting"

            # Test boundary conditions
            user.set_items_per_page(3)  # Below min
            per_page = user.get_items_per_page()
            print(f"✓ Boundary test (3): clamped to {per_page}")
            assert per_page == 5, "Should clamp to minimum 5"

            user.set_items_per_page(150)  # Above max
            per_page = user.get_items_per_page()
            print(f"✓ Boundary test (150): clamped to {per_page}")
            assert per_page == 100, "Should clamp to maximum 100"

            # Reset to default
            user.set_items_per_page(20)
            db.session.commit()
            print(f"✓ Reset to default: 20")

            print("\n✅ User model verification passed!\n")
            return True
        else:
            print("⚠️  No test user found. Run: python init_db.py add-user")
            return False


def verify_routes():
    """Verify routes exist and are accessible."""
    print("=" * 60)
    print("Verifying Routes")
    print("=" * 60)

    with app.test_client() as client:
        # Test preferences route (should redirect to login)
        response = client.get('/preferences')
        print(f"GET /preferences: {response.status_code}")
        assert response.status_code == 302, "Should redirect to login"
        print("✓ /preferences route exists (redirects to login when not authenticated)")

        print("\n✅ Route verification passed!\n")
        return True


def verify_database():
    """Verify database schema."""
    print("=" * 60)
    print("Verifying Database Schema")
    print("=" * 60)

    with app.app_context():
        from sqlalchemy import inspect

        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('users')]

        print(f"User table columns: {', '.join(columns)}")

        if 'preferences' in columns:
            print("✓ preferences column exists")
        else:
            print("✗ preferences column NOT found")
            print("  Run: python init_db.py to create tables")
            return False

        print("\n✅ Database schema verification passed!\n")
        return True


def main():
    """Run all verifications."""
    print("\n" + "=" * 60)
    print("PAGINATION IMPLEMENTATION VERIFICATION")
    print("=" * 60 + "\n")

    try:
        results = {
            'database': verify_database(),
            'user_model': verify_user_model(),
            'routes': verify_routes(),
        }

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)

        all_passed = all(results.values())

        for name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {name.title()}")

        print("=" * 60)

        if all_passed:
            print("\n🎉 All verifications passed! Pagination is ready to use.\n")
            print("Next steps:")
            print("  1. Run: python run.py")
            print("  2. Login with test user")
            print("  3. Navigate to a list with items")
            print("  4. Try the pagination controls")
            print("  5. Go to Profile > Manage Preferences to change items per page\n")
        else:
            print("\n⚠️  Some verifications failed. See above for details.\n")

        return all_passed

    except Exception as e:
        print(f"\n❌ Error during verification: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)

