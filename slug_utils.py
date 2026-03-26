"""
Slug-related utility functions for looking up Groups, Lists, and Items by slug.
This module provides helper functions to retrieve resources using URL-friendly slugs
instead of numeric IDs, supporting both slug-based and ID-based lookups.
"""

from models import db, Group, List, Item


def get_group_by_slug_or_id(slug_or_id):
    """Get a group by slug or ID.
    
    Args:
        slug_or_id: Either a numeric ID or a slug string (e.g., "my-group-123")
    
    Returns:
        Group object or None if not found
    
    Examples:
        get_group_by_slug_or_id(42)              # By ID
        get_group_by_slug_or_id("my-group-42")  # By slug
    """
    # Try as numeric ID first
    if isinstance(slug_or_id, int):
        return Group.query.filter_by(id=slug_or_id).first()
    
    if isinstance(slug_or_id, str):
        # Try to parse as integer
        try:
            group_id = int(slug_or_id)
            return Group.query.filter_by(id=group_id).first()
        except ValueError:
            pass
        
        # Try as slug
        return Group.query.filter_by(slug=slug_or_id).first()
    
    return None


def get_list_by_slug_or_id(slug_or_id, group_id=None):
    """Get a list by slug or ID, optionally filtering by group.
    
    Args:
        slug_or_id: Either a numeric ID or a slug string (e.g., "my-list-123")
        group_id: Optional group ID to filter by (for lists belonging to groups)
    
    Returns:
        List object or None if not found
    
    Examples:
        get_list_by_slug_or_id(42)             # By ID
        get_list_by_slug_or_id("my-list-42")  # By slug
        get_list_by_slug_or_id("my-list-42", group_id=5)  # By slug within a group
    """
    # Build base query
    query = List.query
    
    # Filter by group if specified
    if group_id is not None:
        query = query.filter_by(group_id=group_id)
    
    # Try as numeric ID first
    if isinstance(slug_or_id, int):
        return query.filter_by(id=slug_or_id).first()
    
    if isinstance(slug_or_id, str):
        # Try to parse as integer
        try:
            list_id = int(slug_or_id)
            return query.filter_by(id=list_id).first()
        except ValueError:
            pass
        
        # Try as slug
        return query.filter_by(slug=slug_or_id).first()
    
    return None


def get_list_by_username_and_slug(username, list_slug):
    """Get a personal (non-group) list by username and slug.
    
    Args:
        username: The username of the list owner
        list_slug: The slug of the list
    
    Returns:
        List object or None if not found
    
    Examples:
        get_list_by_username_and_slug("john", "my-list-123")
    """
    from models import User
    
    # Get the user by username
    user = User.query.filter_by(username=username).first()
    if not user:
        return None
    
    # Get the list by user_id and slug (and ensure it's not a group list)
    return List.query.filter_by(user_id=user.id, slug=list_slug, group_id=None).first()


def get_item_by_slug_or_id(slug_or_id):
    """Get an item by slug or ID.
    
    Args:
        slug_or_id: Either a numeric ID or a slug string (e.g., "my-item-123")
    
    Returns:
        Item object or None if not found
    
    Examples:
        get_item_by_slug_or_id(42)             # By ID
        get_item_by_slug_or_id("my-item-42")  # By slug
    """
    # Try as numeric ID first
    if isinstance(slug_or_id, int):
        return Item.query.filter_by(id=slug_or_id).first()
    
    if isinstance(slug_or_id, str):
        # Try to parse as integer
        try:
            item_id = int(slug_or_id)
            return Item.query.filter_by(id=item_id).first()
        except ValueError:
            pass
        
        # Try as slug
        return Item.query.filter_by(slug=slug_or_id).first()
    
    return None
