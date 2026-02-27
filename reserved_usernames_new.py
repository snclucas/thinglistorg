# Reserved Username Blacklist - Loaded from JSON Config
# This module loads reserved words from reserved_usernames.json config file
# to prevent conflicts with system routes, pages, and functionality

import json
import os

# Get the directory where this file is located
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(CONFIG_DIR, 'reserved_usernames.json')

def _load_reserved_usernames():
    """Load reserved usernames from JSON config file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # Flatten all categories into a single set
            all_words = set()
            for category in config.get('reserved_usernames', {}).values():
                all_words.update(category)
            return all_words, config.get('reserved_usernames', {})
    except Exception as e:
        print(f"Error loading reserved usernames from {CONFIG_FILE}: {e}")
        # Return empty sets if file can't be loaded
        return set(), {}

# Load the reserved usernames at module import time
RESERVED_USERNAMES_LOWER, RESERVED_USERNAMES_BY_CATEGORY = _load_reserved_usernames()

def is_username_reserved(username):
    """
    Check if a username is in the reserved words blacklist

    Args:
        username (str): The username to check

    Returns:
        bool: True if username is reserved, False otherwise
    """
    return username.lower() in RESERVED_USERNAMES_LOWER

def get_reserved_username_categories(username):
    """
    Get which categories a reserved username belongs to

    Args:
        username (str): The username to check

    Returns:
        list: List of categories the username is in
    """
    username_lower = username.lower()
    categories = []

    for category_name, words in RESERVED_USERNAMES_BY_CATEGORY.items():
        if username_lower in [w.lower() for w in words]:
            # Convert category name to readable format
            readable_name = category_name.replace('_', ' ').title()
            categories.append(readable_name)

    return categories

def reload_reserved_usernames():
    """
    Reload reserved usernames from config file
    Useful if config file is updated without restarting the app
    """
    global RESERVED_USERNAMES_LOWER, RESERVED_USERNAMES_BY_CATEGORY
    RESERVED_USERNAMES_LOWER, RESERVED_USERNAMES_BY_CATEGORY = _load_reserved_usernames()
    return len(RESERVED_USERNAMES_LOWER)

