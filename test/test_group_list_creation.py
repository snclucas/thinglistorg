#!/usr/bin/env python
"""Test if group_id is being set properly when creating a list in a group"""

from app import app, db
from models import User, Group, List

with app.app_context():
    # Get a user
    user = User.query.first()
    if not user:
        print("No users found in database")
        exit(1)

    print(f"Using user: {user.username}")

    # Get or create a group
    group = Group.query.first()
    if not group:
        print("No groups found in database")
        exit(1)

    print(f"Using group: {group.name} (ID: {group.id})")

    # Check existing lists
    print("\nExisting lists in database:")
    all_lists = List.query.all()
    if all_lists:
        for lst in all_lists[:5]:  # Show first 5
            print(f"  - {lst.name} (ID: {lst.id}, user_id: {lst.user_id}, group_id: {lst.group_id})")
        if len(all_lists) > 5:
            print(f"  ... and {len(all_lists) - 5} more")
    else:
        print("  No lists found")

    # Create a test list in the group
    print(f"\nCreating test list in group {group.name}...")
    test_list = List(
        name=f"Test List for {group.name}",
        description="Test list created in group",
        visibility="private",
        user_id=group.owner_id,  # Set to group owner
        group_id=group.id  # Set group_id
    )
    db.session.add(test_list)
    db.session.commit()

    print(f"\n✓ Created list: {test_list.name}")
    print(f"  ID: {test_list.id}")
    print(f"  user_id: {test_list.user_id}")
    print(f"  group_id: {test_list.group_id}")

    # Verify it was saved
    retrieved = List.query.get(test_list.id)
    if retrieved:
        print(f"\n✓ Retrieved from DB:")
        print(f"  user_id: {retrieved.user_id}")
        print(f"  group_id: {retrieved.group_id}")
        if retrieved.group_id == group.id:
            print(f"\n✓✓ group_id is correctly set in database!")
        else:
            print(f"\n✗ group_id was NOT saved correctly")
    else:
        print("\n✗ Could not retrieve list from database")

