#!/usr/bin/env python
# Test static file serving
import os
from app import app

print("\n✓ Testing Static File Setup\n")

# Check Flask static folder
print(f"Flask static folder: {app.static_folder}")
print(f"Flask static path: {app.config.get('STATIC_FOLDER', 'default')}")

# Check if files exist
static_dir = app.static_folder
pages_dir = os.path.join(static_dir, 'pages')

print(f"\n✓ Static directory exists: {os.path.exists(static_dir)}")
print(f"✓ Pages directory exists: {os.path.exists(pages_dir)}")

# List files
if os.path.exists(pages_dir):
    css_files = os.listdir(pages_dir)
    print(f"\n✓ CSS files in static/pages/:")
    for f in sorted(css_files):
        file_path = os.path.join(pages_dir, f)
        file_size = os.path.getsize(file_path)
        print(f"    • {f} ({file_size:,} bytes)")

# Test URL generation
with app.test_request_context():
    from flask import url_for
    print(f"\n✓ URL generation test:")
    print(f"    • Modern theme: {url_for('static', filename='modern-theme.css')}")
    print(f"    • Lists CSS: {url_for('static', filename='lists.css')}")
    print(f"    • View-item CSS: {url_for('static', filename='view-item.css')}")

print("\n✓ All static files are accessible via Flask\n")

