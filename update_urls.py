#!/usr/bin/env python3
"""Update url_for references to use auth blueprint"""

with open('app.py', 'r') as f:
    content = f.read()

# Replace url_for references
content = content.replace("url_for('login')", "url_for('auth.login')")
content = content.replace("url_for('change_password')", "url_for('auth.change_password')")

with open('app.py', 'w') as f:
    f.write(content)

print("✅ Updated all url_for references to use auth blueprint")
