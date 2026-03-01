from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_from_directory, send_file, Response, current_app, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text, event
from sqlalchemy.orm import attributes
from models import db, User, List, Item, ItemType, Tag, ItemAttachment, AuditLog, item_tags, ListCustomField, ItemCustomField, ListShare, Notification, ItemImage, Group, GroupMember, Location
from forms import RegistrationForm, LoginForm, CreateGroupForm, EditGroupForm, AddGroupMemberForm, EditGroupMemberForm, ForgotPasswordForm, ResetPasswordForm, PasswordChangeForm, ItemTypeForm, LocationForm
from config import config
from auth_routes import auth_bp
from list_item_routes import list_item_bp, _log_action
from slug_utils import get_group_by_slug_or_id
from flask_wtf.csrf import CSRFError, CSRFProtect
import os
import csv
import io
import json
import time
import uuid
import datetime
import logging
from PIL import Image, UnidentifiedImageError
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to console
    ]
)

# Get logger for the app
app.logger.setLevel(logging.INFO)

# Add console handler to app logger
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
app.logger.addHandler(console_handler)

# Log app startup
app.logger.info(f'Flask application starting in {os.environ.get("FLASK_ENV", "development")} mode...')

# Load configuration based on environment
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[env])

# File upload settings
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = app.config.get('IMAGE_MAX_SIZE', 16 * 1024 * 1024)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['IMAGE_STORAGE_DIR'], exist_ok=True)
app.logger.info(f'Upload folder configured: {app.config["UPLOAD_FOLDER"]}')
app.logger.info(f'Image storage folder configured: {app.config["IMAGE_STORAGE_DIR"]}')

# Initialize database
db.init_app(app)
app.logger.info('Database initialized')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'
app.logger.info('Flask-Login initialized')

# Initialize Flask-WTF for CSRF protection
csrf = CSRFProtect(app)
app.logger.info('Flask-WTF CSRF protection initialized')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])
app.logger.info('Rate limiting initialized')

# Register Blueprint for Auth Routes
app.register_blueprint(auth_bp)

# Register Blueprint for List & Item Routes
app.register_blueprint(list_item_bp)

# Security Headers Middleware
@app.after_request
def set_security_headers(response):
    """Set security headers on all responses"""
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # Enable XSS protection (for older browsers)
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # Clickjacking protection
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'

    # Referrer Policy - limits referrer information
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Permissions Policy (formerly Feature Policy) - controls browser features
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), payment=()'

    # Content Security Policy - prevents various attacks
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "connect-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers['Content-Security-Policy'] = csp

    # HSTS - force HTTPS (only in production)
    if app.config.get('ENV') == 'production' or os.environ.get('FLASK_ENV') == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    # Reduce information leakage
    response.headers['Server'] = 'Production Server'

    return response

# Trust proxy headers (for Gunicorn behind nginx/apache)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# CSRF Error Handler
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF token errors"""
    app.logger.warning(f'CSRF Error: {e.description}')
    # Log request details for debugging
    app.logger.debug(f'  Request method: {request.method}')
    app.logger.debug(f'  Request path: {request.path}')
    app.logger.debug(f'  Referrer: {request.referrer}')
    app.logger.debug(f'  Origin: {request.origin}')
    app.logger.debug(f'  Host: {request.host}')
    app.logger.debug(f'  X-Forwarded-Proto: {request.headers.get("X-Forwarded-Proto")}')
    app.logger.debug(f'  Session cookie secure: {app.config.get("SESSION_COOKIE_SECURE")}')
    flash('Security token expired or invalid. Please refresh and try again.', 'error')
    return redirect(request.referrer or url_for('index'))

def _get_unique_id(table_name, entity_id):
    """Fetch unique_id from database using raw SQL
    
    Used during migration period when unique_id column exists in DB but not in ORM model.
    If unique_id doesn't exist or is NULL, generates a new UUID and stores it.
    """
    try:
        result = db.session.execute(
            text(f'SELECT unique_id FROM {table_name} WHERE id = :id'),
            {'id': entity_id}
        ).fetchone()
        
        unique_id = result[0] if result and result[0] else None
        
        # If no unique_id, generate one
        if not unique_id:
            unique_id = str(uuid.uuid4())
            # Store the generated UUID
            db.session.execute(
                text(f'UPDATE {table_name} SET unique_id = :uid WHERE id = :id'),
                {'uid': unique_id, 'id': entity_id}
            )
            try:
                db.session.commit()
            except:
                db.session.rollback()
        
        return unique_id
    except Exception as e:
        app.logger.error(f'Error fetching unique_id from {table_name}: {str(e)}')
        # Fallback: generate and return a UUID
        return str(uuid.uuid4())


@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/sitemap.xml')
@limiter.exempt
def sitemap():
    """Generate XML sitemap for SEO"""
    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # Get base URL
    base_url = request.base_url.rstrip('/')

    # Add main pages
    pages = [
        ('/', 1.0, 'daily'),
        ('/public-lists', 0.9, 'daily'),
    ]

    for url, priority, changefreq in pages:
        sitemap_xml += f'  <url>\n'
        sitemap_xml += f'    <loc>{base_url}{url}</loc>\n'
        sitemap_xml += f'    <priority>{priority}</priority>\n'
        sitemap_xml += f'    <changefreq>{changefreq}</changefreq>\n'
        sitemap_xml += f'  </url>\n'

    # Add public lists
    try:
        public_lists = List.query.filter_by(visibility='public').all()
        for lst in public_lists:
            sitemap_xml += f'  <url>\n'
            sitemap_xml += f'    <loc>{base_url}/lists/{lst.id}</loc>\n'
            sitemap_xml += f'    <lastmod>{lst.updated_at.isoformat()}</lastmod>\n'
            sitemap_xml += f'    <priority>0.8</priority>\n'
            sitemap_xml += f'    <changefreq>weekly</changefreq>\n'
            sitemap_xml += f'  </url>\n'
    except Exception as e:
        app.logger.error(f'Error generating sitemap for public lists: {str(e)}')

    sitemap_xml += '</urlset>'

    response = Response(sitemap_xml, mimetype='application/xml')
    response.headers['Cache-Control'] = 'public, max-age=86400'  # Cache for 1 day
    return response

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard (protected)"""
    # Get user's groups
    owned_groups = Group.query.filter_by(owner_id=current_user.id).order_by(Group.created_at.desc()).all()

    # Get groups user is a member of (excluding owned)
    member_groups = []
    owned_group_ids = {group.id for group in owned_groups}
    for membership in current_user.group_memberships:
        if membership.group_id not in owned_group_ids:
            member_groups.append(membership.group)
    member_groups.sort(key=lambda g: g.created_at, reverse=True)

    # Get user's lists
    user_lists = List.query.filter_by(user_id=current_user.id, group_id=None).order_by(List.created_at.desc()).limit(5).all()

    # Get shared lists
    from sqlalchemy import and_
    shared_lists = List.query.join(ListShare, ListShare.list_id == List.id).filter(
        ListShare.user_id == current_user.id
    ).order_by(List.created_at.desc()).limit(5).all()

    return render_template(
        'dashboard.html',
        user=current_user,
        owned_groups=owned_groups,
        member_groups=member_groups,
        user_lists=user_lists,
        shared_lists=shared_lists
    )


@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    """User profile (protected)"""
    unread_count = current_user.get_unread_notifications_count()
    return render_template('profile.html', user=current_user, unread_notifications_count=unread_count)


@app.route('/preferences', methods=['GET', 'POST'])
@login_required
def user_preferences():
    """User preferences page"""
    if request.method == 'POST':
        # Update items per page preference
        items_per_page = request.form.get('items_per_page', None)
        if items_per_page:
            try:
                current_user.set_items_per_page(int(items_per_page))
                db.session.commit()
                flash('Preferences updated successfully!', 'success')
            except (ValueError, TypeError):
                flash('Invalid items per page value.', 'error')
        return redirect(url_for('user_preferences'))

    unread_count = current_user.get_unread_notifications_count()
    items_per_page = current_user.get_items_per_page()
    return render_template('preferences.html', user=current_user, items_per_page=items_per_page, unread_notifications_count=unread_count)




# ============================================================================
# GROUP MANAGEMENT ROUTES
# ============================================================================# ============================================================================
# GROUP MANAGEMENT ROUTES
# ============================================================================

@app.route('/groups')
@login_required
def view_groups():
    """View all groups for the current user"""
    # Get groups owned by the user
    owned_groups = Group.query.filter_by(owner_id=current_user.id).order_by(Group.created_at.desc()).all()

    # Get groups the user is a member of (excluding ones they own)
    member_groups = []
    owned_group_ids = {group.id for group in owned_groups}

    for membership in current_user.group_memberships:
        # Only include groups they don't own
        if membership.group_id not in owned_group_ids:
            member_groups.append(membership.group)

    member_groups.sort(key=lambda g: g.created_at, reverse=True)

    return render_template(
        'groups/list.html',
        owned_groups=owned_groups,
        member_groups=member_groups
    )


@app.route('/groups/create', methods=['GET', 'POST'])
@login_required
def create_group():
    """Create a new group"""
    form = CreateGroupForm()

    if form.validate_on_submit():
        group = Group(
            name=form.name.data,
            description=form.description.data,
            owner_id=current_user.id
        )
        group.set_settings({
            'allow_members_create_lists': form.allow_members_create_lists.data,
            'allow_members_edit_shared_lists': form.allow_members_edit_shared_lists.data,
        })

        db.session.add(group)
        db.session.commit()

        # Generate slug now that group has an ID
        group.generate_slug()
        db.session.commit()

        # Owner is automatically an admin
        group.add_member(current_user.id, role='admin')
        db.session.commit()

        flash(f'Group "{group.name}" created successfully!', 'success')
        return redirect(url_for('view_group', group_id=group.slug))

    return render_template('groups/create.html', form=form)


@app.route('/groups/<group_id>')
@login_required
def view_group(group_id):
    """View group details and members"""
    group = get_group_by_slug_or_id(group_id)
    if not group:
        abort(404)

    # Check if user has access to this group
    if not group.is_owner(current_user.id) and not group.get_member(current_user.id):
        flash('You do not have access to this group.', 'danger')
        return redirect(url_for('view_groups'))

    members = group.get_members()
    lists = List.query.filter_by(group_id=group.id).order_by(List.created_at.desc()).all()

    return render_template(
        'groups/view.html',
        group=group,
        members=members,
        lists=lists,
        is_owner=group.is_owner(current_user.id),
        is_admin=group.is_admin(current_user.id)
    )


@app.route('/groups/<group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    """Edit group settings (admin only)"""
    group = get_group_by_slug_or_id(group_id)
    if not group:
        abort(404)

    # Only owner can edit group settings
    if not group.is_owner(current_user.id):
        flash('You do not have permission to edit this group.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    form = EditGroupForm()

    if form.validate_on_submit():
        group.name = form.name.data
        group.description = form.description.data
        group.set_settings({
            'allow_members_create_lists': form.allow_members_create_lists.data,
            'allow_members_edit_shared_lists': form.allow_members_edit_shared_lists.data,
        })
        db.session.commit()

        flash('Group settings updated successfully!', 'success')
        return redirect(url_for('view_group', group_id=group_id))

    # Pre-populate form
    if request.method == 'GET':
        form.name.data = group.name
        form.description.data = group.description
        settings = group.get_settings()
        form.allow_members_create_lists.data = settings.get('allow_members_create_lists', True)
        form.allow_members_edit_shared_lists.data = settings.get('allow_members_edit_shared_lists', True)

    return render_template('groups/edit.html', form=form, group=group)


@app.route('/groups/<group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Delete a group (owner only)"""
    group = get_group_by_slug_or_id(group_id)
    if not group:
        abort(404)

    # Only owner can delete
    if not group.is_owner(current_user.id):
        flash('You do not have permission to delete this group.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    group_name = group.name
    db.session.delete(group)
    db.session.commit()

    flash(f'Group "{group_name}" deleted successfully!', 'success')
    return redirect(url_for('view_groups'))


@app.route('/groups/<group_id>/members/add', methods=['GET', 'POST'])
@login_required
def add_group_member(group_id):
    """Add a member to the group (admin only)"""
    group = get_group_by_slug_or_id(group_id)
    if not group:
        abort(404)

    # Only admin or owner can add members
    if not group.is_admin(current_user.id):
        flash('You do not have permission to add members to this group.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    form = AddGroupMemberForm()

    if form.validate_on_submit():
        user = form.user

        # Check if user is already a member
        if group.get_member(user.id):
            flash(f'User "{user.username}" is already a member of this group.', 'warning')
        else:
            group.add_member(user.id, role=form.role.data)
            db.session.commit()
            flash(f'User "{user.username}" added to group as {form.role.data}!', 'success')
            return redirect(url_for('view_group', group_id=group_id))

    return render_template('groups/add_member.html', form=form, group=group)


@app.route('/groups/<group_id>/members/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group_member(group_id, user_id):
    """Edit a group member's role and permissions (admin only)"""
    group = get_group_by_slug_or_id(group_id)
    if not group:
        abort(404)

    # Only admin can edit members
    if not group.is_admin(current_user.id):
        flash('You do not have permission to edit group members.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    member = group.get_member(user_id)
    if not member:
        flash('Member not found.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    # Cannot edit owner
    if group.is_owner(user_id):
        flash('Cannot edit the group owner.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    form = EditGroupMemberForm()

    if form.validate_on_submit():
        member.role = form.role.data
        db.session.commit()

        flash(f'Member role updated to {form.role.data}!', 'success')
        return redirect(url_for('view_group', group_id=group_id))

    if request.method == 'GET':
        form.role.data = member.role

    return render_template('groups/edit_member.html', form=form, group=group, member=member)


@app.route('/groups/<group_id>/members/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_group_member(group_id, user_id):
    """Remove a member from the group (admin only)"""
    group = get_group_by_slug_or_id(group_id)
    if not group:
        abort(404)

    # Only admin can remove members
    if not group.is_admin(current_user.id):
        flash('You do not have permission to remove members.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    # Cannot remove owner
    if group.is_owner(user_id):
        flash('Cannot remove the group owner.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    member = group.get_member(user_id)
    if member:
        user = member.user
        group.remove_member(user_id)
        db.session.commit()
        flash(f'User "{user.username}" removed from group.', 'success')
    else:
        flash('Member not found.', 'danger')

    return redirect(url_for('view_group', group_id=group_id))


# Item Type Management Routes
@app.route('/item-types', methods=['GET'])
@login_required
def list_item_types():
    """List all item types for the current user"""
    # Get user's custom item types
    item_types = ItemType.query.filter_by(user_id=current_user.id, is_system=False).order_by(ItemType.name).all()
    
    # Count items using each type
    type_counts = {}
    for item_type in item_types:
        type_counts[item_type.id] = Item.query.filter_by(item_type_id=item_type.id).count()
    
    return render_template('item_types.html', item_types=item_types, type_counts=type_counts)


@app.route('/item-types/create', methods=['GET', 'POST'])
@login_required
def create_item_type():
    """Create a new item type"""
    from forms import ItemTypeForm
    
    form = ItemTypeForm()
    if form.validate_on_submit():
        try:
            item_type = ItemType(
                name=form.name.data,
                is_system=False,
                user_id=current_user.id
            )
            db.session.add(item_type)
            db.session.commit()
            flash(f'Item type "{item_type.name}" created successfully.', 'success')
            return redirect(url_for('list_item_types'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the item type.', 'error')
            app.logger.error(f'Error creating item type: {str(e)}')
    
    return render_template('create_item_type.html', form=form)


@app.route('/item-types/<int:item_type_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item_type(item_type_id):
    """Edit an item type"""
    from forms import ItemTypeForm
    
    item_type = ItemType.query.get_or_404(item_type_id)
    
    # Check if user owns this item type
    if item_type.user_id != current_user.id:
        flash('You do not have permission to edit this item type.', 'error')
        return redirect(url_for('list_item_types'))
    
    form = ItemTypeForm()
    if form.validate_on_submit():
        try:
            # Check for unique name among user's types
            existing = ItemType.query.filter(
                ItemType.name == form.name.data,
                ItemType.user_id == current_user.id,
                ItemType.id != item_type_id,
                ItemType.is_system == False
            ).first()
            
            if existing:
                flash('An item type with this name already exists.', 'error')
                return render_template('edit_item_type.html', form=form, item_type=item_type)
            
            item_type.name = form.name.data
            db.session.commit()
            flash(f'Item type "{item_type.name}" updated successfully.', 'success')
            return redirect(url_for('list_item_types'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the item type.', 'error')
            app.logger.error(f'Error updating item type: {str(e)}')
    
    if request.method == 'GET':
        form.name.data = item_type.name
    
    # Count items using this type
    item_count = Item.query.filter_by(item_type_id=item_type_id).count()
    
    return render_template('edit_item_type.html', form=form, item_type=item_type, item_count=item_count)


@app.route('/item-types/<int:item_type_id>/delete', methods=['POST'])
@login_required
def delete_item_type(item_type_id):
    """Delete an item type (sets items to NULL item_type_id)"""
    item_type = ItemType.query.get_or_404(item_type_id)
    
    # Check if user owns this item type
    if item_type.user_id != current_user.id:
        flash('You do not have permission to delete this item type.', 'error')
        return redirect(url_for('list_item_types'))
    
    try:
        type_name = item_type.name
        
        # Set item_type_id to NULL for all items using this type
        Item.query.filter_by(item_type_id=item_type_id).update({Item.item_type_id: None})
        
        # Delete the item type
        db.session.delete(item_type)
        db.session.commit()
        
        flash(f'Item type "{type_name}" deleted successfully. Items are no longer assigned to this type.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the item type.', 'error')
        app.logger.error(f'Error deleting item type: {str(e)}')
    
    return redirect(url_for('list_item_types'))


@app.route('/locations', methods=['GET'])
@login_required
def list_locations():
    """List all locations for the current user"""
    # Get user's custom locations
    locations = Location.query.filter_by(user_id=current_user.id, is_system=False).order_by(Location.name).all()
    
    # Count items using each location
    location_counts = {}
    for location in locations:
        location_counts[location.id] = Item.query.filter_by(location_id=location.id).count()
    
    return render_template('locations.html', locations=locations, location_counts=location_counts)


@app.route('/locations/create', methods=['GET', 'POST'])
@login_required
def create_location():
    """Create a new location"""
    from forms import LocationForm
    
    form = LocationForm()
    if form.validate_on_submit():
        try:
            location = Location(
                name=form.name.data,
                is_system=False,
                user_id=current_user.id
            )
            db.session.add(location)
            db.session.commit()
            flash(f'Location "{location.name}" created successfully.', 'success')
            return redirect(url_for('list_locations'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the location.', 'error')
            app.logger.error(f'Error creating location: {str(e)}')
    
    return render_template('create_location.html', form=form)


@app.route('/locations/<int:location_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_location(location_id):
    """Edit a location"""
    from forms import LocationForm
    
    location = Location.query.get_or_404(location_id)
    
    # Check if user owns this location
    if location.user_id != current_user.id:
        flash('You do not have permission to edit this location.', 'error')
        return redirect(url_for('list_locations'))
    
    form = LocationForm()
    if form.validate_on_submit():
        try:
            # Check for unique name among user's locations
            existing = Location.query.filter(
                Location.name == form.name.data,
                Location.user_id == current_user.id,
                Location.id != location_id,
                Location.is_system == False
            ).first()
            
            if existing:
                flash('A location with this name already exists.', 'error')
                return render_template('edit_location.html', form=form, location=location)
            
            location.name = form.name.data
            db.session.commit()
            flash(f'Location "{location.name}" updated successfully.', 'success')
            return redirect(url_for('list_locations'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the location.', 'error')
            app.logger.error(f'Error updating location: {str(e)}')
    
    if request.method == 'GET':
        form.name.data = location.name
    
    # Count items using this location
    item_count = Item.query.filter_by(location_id=location_id).count()
    
    return render_template('edit_location.html', form=form, location=location, item_count=item_count)


@app.route('/locations/<int:location_id>/delete', methods=['POST'])
@login_required
def delete_location(location_id):
    """Delete a location (sets items to NULL location_id)"""
    location = Location.query.get_or_404(location_id)
    
    # Check if user owns this location
    if location.user_id != current_user.id:
        flash('You do not have permission to delete this location.', 'error')
        return redirect(url_for('list_locations'))
    
    try:
        location_name = location.name
        
        # Set location_id to NULL for all items using this location
        Item.query.filter_by(location_id=location_id).update({Item.location_id: None})
        
        # Delete the location
        db.session.delete(location)
        db.session.commit()
        
        flash(f'Location "{location_name}" deleted successfully. Items are no longer assigned to this location.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the location.', 'error')
        app.logger.error(f'Error deleting location: {str(e)}')
    
    return redirect(url_for('list_locations'))


@app.route('/notifications', methods=['GET'])
@login_required
def view_notifications():
    """View all user notifications"""
    # Get all notifications for current user
    page = max(int(request.args.get('page', 1)), 1)
    per_page = 20

    notifications_query = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc())
    total = notifications_query.count()
    notifications = notifications_query.offset((page - 1) * per_page).limit(per_page).all()

    pages = (total + per_page - 1) // per_page if total else 1
    unread_count = current_user.get_unread_notifications_count()

    return render_template('notifications.html',
                         notifications=notifications,
                         total=total,
                         page=page,
                         pages=pages,
                         unread_count=unread_count)


@app.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    notification = Notification.query.get_or_404(notification_id)

    # Verify user owns this notification
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    notification.mark_as_read()
    db.session.commit()

    return jsonify({'success': True, 'is_read': notification.is_read})


@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    for notification in unread_notifications:
        notification.is_read = True
    db.session.commit()

    return jsonify({'success': True, 'marked': len(unread_notifications)})


@app.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    notification = Notification.query.get_or_404(notification_id)

    # Verify user owns this notification
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    db.session.delete(notification)
    db.session.commit()

    return jsonify({'success': True})


# NOTE: Custom field routes have been moved to list_item_routes.py


# NOTE: Item management, import/export, and attachment routes moved to list_item_routes.py


@app.route('/image-content/<path:filename>')


@app.route('/image-content/<path:filename>')
def image_content(filename):
    return send_from_directory(app.config['IMAGE_STORAGE_DIR'], filename)


@app.route('/alerts')
@login_required
def alerts():
    low_stock_items = Item.query.join(List).filter(
        List.user_id == current_user.id,
        Item.low_stock_threshold > 0,
        Item.quantity <= Item.low_stock_threshold
    ).all()
    reminders_due = Item.query.join(List).filter(
        List.user_id == current_user.id,
        Item.reminder_at.isnot(None),
        Item.reminder_at <= datetime.datetime.utcnow()
    ).all()
    return render_template('alerts.html', low_stock_items=low_stock_items, reminders_due=reminders_due)


# ============= API Endpoints (Autocomplete routes moved to list_item_routes.py) =============


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    return render_template('500.html'), 500


def _build_item_query(list_id, args):
    """Build filtered item query for a list."""
    query = Item.query.filter_by(list_id=list_id)

    q = (args.get('q') or '').strip()
    tag = (args.get('tag') or '').strip().lower()
    item_type = (args.get('type') or '').strip()
    location = (args.get('location') or '').strip()
    low_stock = args.get('low_stock') == '1'
    min_qty = (args.get('min_qty') or '').strip()
    max_qty = (args.get('max_qty') or '').strip()
    reminder_due = args.get('reminder_due') == '1'

    if q:
        query = query.filter(
            db.or_(
                Item.name.ilike(f'%{q}%'),
                Item.description.ilike(f'%{q}%'),
                Item.notes.ilike(f'%{q}%')
            )
        )
    if tag:
        query = query.filter(Item.tags_rel.any(Tag.name == tag))
    if item_type:
        query = query.filter(Item.item_type.has(ItemType.name == item_type))
    if location:
        query = query.filter(Item.location.ilike(f'%{location}%'))
    if low_stock:
        query = query.filter(Item.low_stock_threshold > 0, Item.quantity <= Item.low_stock_threshold)
    if min_qty.isdigit():
        query = query.filter(Item.quantity >= int(min_qty))
    if max_qty.isdigit():
        query = query.filter(Item.quantity <= int(max_qty))
    if reminder_due:
        query = query.filter(Item.reminder_at.isnot(None), Item.reminder_at <= datetime.datetime.utcnow())

    return query


class BooleanQueryParser:
    """Parse and evaluate boolean search queries with AND, OR, NOT operators and brackets."""

    def __init__(self, query_string):
        self.query_string = query_string.strip()
        self.tokens = self._tokenize()
        self.pos = 0

    def _tokenize(self):
        """Tokenize the query string into meaningful parts."""
        tokens = []
        i = 0
        while i < len(self.query_string):
            if self.query_string[i].isspace():
                i += 1
                continue

            # Handle brackets
            if self.query_string[i] in '()':
                tokens.append(self.query_string[i])
                i += 1
            # Handle quoted phrases
            elif self.query_string[i] == '"':
                i += 1
                phrase = ''
                while i < len(self.query_string) and self.query_string[i] != '"':
                    phrase += self.query_string[i]
                    i += 1
                if i < len(self.query_string):
                    i += 1
                if phrase:
                    tokens.append(f'"{phrase}"')
            # Handle regular words/operators
            else:
                word = ''
                while i < len(self.query_string) and not self.query_string[i].isspace() and self.query_string[i] not in '()':
                    word += self.query_string[i]
                    i += 1
                if word:
                    tokens.append(word)

        return tokens

    def _is_operator(self, token):
        """Check if token is an operator."""
        return token.upper() in ('AND', 'OR', 'NOT')

    def _current_token(self):
        """Get current token without consuming."""
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume_token(self):
        """Consume and return current token."""
        token = self._current_token()
        self.pos += 1
        return token

    def parse(self):
        """Parse query into AST."""
        if not self.tokens:
            return None
        self.pos = 0  # Reset position for fresh parse
        result = self._parse_or()
        return result

    def _parse_or(self):
        """Parse OR expressions (lowest precedence)."""
        left = self._parse_and()

        while self._current_token() and self._current_token().upper() == 'OR':
            self._consume_token()
            right = self._parse_and()
            left = ('OR', left, right)

        return left

    def _parse_and(self):
        """Parse AND expressions (medium precedence)."""
        left = self._parse_not()

        while self._current_token() and self._current_token().upper() == 'AND':
            self._consume_token()
            right = self._parse_not()
            left = ('AND', left, right)

        return left

    def _parse_not(self):
        """Parse NOT expressions."""
        if self._current_token() and self._current_token().upper() == 'NOT':
            self._consume_token()
            operand = self._parse_primary()
            return ('NOT', operand)

        return self._parse_primary()

    def _parse_primary(self):
        """Parse primary expressions (terms and bracketed expressions)."""
        token = self._current_token()

        if token == '(':  # bracketed expression
            self._consume_token()
            result = self._parse_or()
            if self._current_token() == ')':
                self._consume_token()
            return result
        elif token and not self._is_operator(token) and token != ')':
            self._consume_token()
            return ('TERM', token.strip('"'))
        elif token in (None, ')'):
            # Gracefully handle trailing operators, stray closing parens, or unexpected end
            return ('EMPTY', None)
        else:
            raise ValueError(f"Unexpected token: {token}")

    def _evaluate_ast(self, ast, text):
        """Evaluate AST node."""
        if ast is None:
            return True

        if ast[0] == 'TERM':
            return ast[1].lower() in text
        elif ast[0] == 'AND':
            return self._evaluate_ast(ast[1], text) and self._evaluate_ast(ast[2], text)
        elif ast[0] == 'OR':
            return self._evaluate_ast(ast[1], text) or self._evaluate_ast(ast[2], text)
        elif ast[0] == 'NOT':
            return not self._evaluate_ast(ast[1], text)
        elif ast[0] == 'EMPTY':
            return True

        return True

    def evaluate(self, text):
        """Evaluate parsed query against a text blob (case-insensitive)."""
        ast = self.parse()
        if ast is None:
            return True
        return self._evaluate_ast(ast, (text or '').lower())

    def to_sql_filter(self, *columns):
        """Convert parsed query to SQLAlchemy filter."""
        ast = self.parse()
        if ast is None:
            return True
        return self._ast_to_sql(ast, columns)

    def _ast_to_sql(self, ast, columns):
        """Convert AST to SQLAlchemy filter."""
        if ast is None:
            return True

        if ast[0] == 'TERM':
            conditions = [col.ilike(f'%{ast[1]}%') for col in columns]
            return db.or_(*conditions) if conditions else True
        elif ast[0] == 'AND':
            left = self._ast_to_sql(ast[1], columns)
            right = self._ast_to_sql(ast[2], columns)
            return db.and_(left, right)
        elif ast[0] == 'OR':
            left = self._ast_to_sql(ast[1], columns)
            right = self._ast_to_sql(ast[2], columns)
            return db.or_(left, right)
        elif ast[0] == 'NOT':
            operand = self._ast_to_sql(ast[1], columns)
            return ~operand
        elif ast[0] == 'EMPTY':
            return True

        return True


@app.route('/search')
def search():
    """Comprehensive search for lists and items with boolean logic support"""
    # Get search parameters
    query = request.args.get('q', '').strip()
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 5), 100)

    # Get search scope checkboxes (default all checked)
    search_all = request.args.get('all', 'on') == 'on'
    search_description = request.args.get('description', 'on') == 'on' or search_all
    search_tags = request.args.get('tags', 'on') == 'on' or search_all
    search_locations = request.args.get('locations', 'on') == 'on' or search_all
    search_notes = request.args.get('notes', 'on') == 'on' or search_all

    # For authenticated users, option to include public content
    include_public = request.args.get('include_public', 'off') == 'on'

    lists_results = []
    items_results = []
    total_lists = 0
    total_items = 0
    boolean_error = None

    if query:
        try:
            # Parse boolean query
            parser = BooleanQueryParser(query)

            # Build list query
            list_query = List.query

            # Apply access control for lists
            if current_user.is_authenticated:
                # Get group IDs that user is a member of
                user_group_ids = [gm.group_id for gm in current_user.group_memberships]

                if include_public:
                    list_query = list_query.filter(
                        db.or_(
                            List.user_id == current_user.id,  # User's own lists
                            List.id.in_(
                                db.session.query(ListShare.list_id).filter(ListShare.user_id == current_user.id)
                            ),  # Shared lists
                            List.group_id.in_(user_group_ids),  # Lists in groups user is a member of
                            List.visibility == 'public'  # Public lists
                        )
                    )
                else:
                    list_query = list_query.filter(
                        db.or_(
                            List.user_id == current_user.id,  # User's own lists
                            List.id.in_(
                                db.session.query(ListShare.list_id).filter(ListShare.user_id == current_user.id)
                            ),  # Shared lists
                            List.group_id.in_(user_group_ids)  # Lists in groups user is a member of
                        )
                    )
            else:
                list_query = list_query.filter(List.visibility == 'public')

            # Get all lists for filtering (before pagination)
            all_lists = list_query.all()

            # Apply boolean filter to lists
            list_search_text_list = []
            for lst in all_lists:
                search_text = lst.name
                if search_description and lst.description:
                    search_text += ' ' + lst.description
                if search_tags and lst.tags:
                    search_text += ' ' + lst.tags

                if parser.evaluate(search_text):
                    list_search_text_list.append(lst)

            # Sort and paginate
            list_search_text_list.sort(key=lambda x: x.created_at, reverse=True)
            total_lists = len(list_search_text_list)
            lists_results = list_search_text_list[:20]

            # Build item query
            item_query = Item.query.join(List, Item.list_id == List.id)

            # Apply access control for items
            if current_user.is_authenticated:
                # Get group IDs that user is a member of
                user_group_ids = [gm.group_id for gm in current_user.group_memberships]

                if include_public:
                    item_query = item_query.filter(
                        db.or_(
                            List.user_id == current_user.id,  # User's own lists
                            List.id.in_(
                                db.session.query(ListShare.list_id).filter(ListShare.user_id == current_user.id)
                            ),  # Shared lists
                            List.group_id.in_(user_group_ids),  # Lists in groups user is a member of
                            List.visibility == 'public'  # Public lists
                        )
                    )
                else:
                    item_query = item_query.filter(
                        db.or_(
                            List.user_id == current_user.id,  # User's own lists
                            List.id.in_(
                                db.session.query(ListShare.list_id).filter(ListShare.user_id == current_user.id)
                            ),  # Shared lists
                            List.group_id.in_(user_group_ids)  # Lists in groups user is a member of
                        )
                    )
            else:
                item_query = item_query.filter(List.visibility == 'public')

            # Get all items for filtering
            all_items = item_query.all()

            # Apply boolean filter to items
            item_search_text_list = []
            for item in all_items:
                search_text = item.name
                if search_description and item.description:
                    search_text += ' ' + item.description
                if search_notes and item.notes:
                    search_text += ' ' + item.notes
                if search_tags and item.tags:
                    search_text += ' ' + item.tags
                if search_locations and item.location:
                    search_text += ' ' + item.location

                if parser.evaluate(search_text):
                    item_search_text_list.append(item)

            # Sort and paginate
            item_search_text_list.sort(key=lambda x: x.created_at, reverse=True)
            total_items = len(item_search_text_list)
            items_results = item_search_text_list[:20]

        except ValueError as e:
            boolean_error = f"Invalid query syntax: {str(e)}"

    return render_template(
        'search.html',
        query=query,
        lists=lists_results,
        items=items_results,
        total_lists=total_lists,
        total_items=total_items,
        page=page,
        per_page=per_page,
        search_all=search_all,
        search_description=search_description,
        search_tags=search_tags,
        search_locations=search_locations,
        search_notes=search_notes,
        include_public=include_public,
        boolean_error=boolean_error,
        get_list_access_type=_get_list_access_type,
        current_user_id=current_user.id if current_user.is_authenticated else None
    )


@app.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    """Verify user email with token"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    try:
        user = User.query.filter_by(email_verification_token=token).first()

        if not user:
            flash('Invalid verification link.', 'error')
            return redirect(url_for('auth.login'))

        if not user.verify_email_token(token):
            flash('Verification link has expired. Please register again.', 'error')
            return redirect(url_for('auth.register'))

        user.confirm_email()
        db.session.commit()

        flash('Email verified successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    except Exception as e:
        app.logger.error(f'Email verification error: {str(e)}')
        flash('An error occurred during verification. Please try again.', 'error')
        return redirect(url_for('auth.login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def forgot_password():
    """Request password reset"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        try:
            from email_utils import generate_token, send_password_reset_email

            user = User.query.filter_by(email=form.email.data.lower()).first()

            if user:
                # Generate reset token
                reset_token = generate_token()
                user.set_password_reset_token(reset_token)
                db.session.commit()

                # Send password reset email
                base_url = request.host_url.rstrip('/')
                send_password_reset_email(user, reset_token, base_url)

            # Always show success message for security (don't reveal if email exists)
            flash('If an account with that email exists, a password reset link has been sent.', 'info')
            return redirect(url_for('auth.login'))

        except Exception as e:
            app.logger.error(f'Password reset request error: {str(e)}')
            flash('An error occurred. Please try again.', 'error')

    return render_template('forgot_password.html', form=form)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def reset_password(token):
    """Reset password with token"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    user = User.query.filter_by(password_reset_token=token).first()

    if not user or not user.verify_password_reset_token(token):
        flash('Invalid or expired password reset link.', 'error')
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            if user.reset_password(token, form.password.data):
                db.session.commit()
                flash('Your password has been reset successfully. You can now log in.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Password reset failed. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Password reset error: {str(e)}')
            flash('An error occurred during password reset. Please try again.', 'error')

    return render_template('reset_password.html', form=form, token=token)



@app.route('/resend-verification-email', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def resend_verification_email():
    """Resend verification email to user"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()

            if not email:
                flash('Please enter your email address.', 'error')
                return redirect(url_for('resend_verification_email'))

            user = User.query.filter_by(email=email).first()

            if not user:
                # Don't reveal if email exists (security best practice)
                flash('If an account with that email exists and is not verified, a verification link has been sent.', 'info')
                return redirect(url_for('auth.login'))

            if user.email_verified:
                flash('Your email is already verified! You can log in now.', 'success')
                return redirect(url_for('auth.login'))

            # Generate new verification token
            from email_utils import generate_token, send_verification_email

            verification_token = generate_token()
            user.set_email_verification_token(verification_token)
            db.session.commit()

            # Send verification email
            base_url = request.host_url.rstrip('/')
            send_verification_email(user, verification_token, base_url)

            flash('Verification email sent! Please check your inbox for the verification link.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Resend verification email error: {str(e)}')
            flash('An error occurred while sending the verification email. Please try again.', 'error')
            return redirect(url_for('resend_verification_email'))

    return render_template('resend_verification_email.html')


def _get_list_access_type(lst, current_user_id):
    """Determine the type of access a user has to a list for display purposes"""
    if not current_user_id:
        # Anonymous user
        if lst.visibility == 'public':
            return 'public'
        return None

    # Logged in user
    if lst.user_id == current_user_id:
        return 'own'

    if lst.visibility == 'public':
        return 'public'

    # Check if shared
    share = ListShare.query.filter_by(list_id=lst.id, user_id=current_user_id).first()
    if share:
        return 'shared'

    # Check if in group
    if lst.group_id:
        member = GroupMember.query.filter_by(group_id=lst.group_id, user_id=current_user_id).first()
        if member:
            return 'group'

    return None


# ===== GDPR COMPLIANCE ROUTES =====

@app.route('/gdpr/export-data')
@login_required
def export_data():
    """Export user's personal data in JSON format (GDPR right to data portability)
    Uses unique_id instead of database IDs for portability and privacy"""
    try:
        import json
        from io import BytesIO

        # Collect all user data - using unique_ids instead of database IDs
        user_data = {
            'version': '1.0',
            'export_type': 'account_data',
            'username': current_user.username,
            'email': current_user.email,
            'preferences': current_user.preferences or {},
            'groups': [],
            'lists': [],
            'items': [],
            'list_shares': [],
        }

        # Collect groups owned (with unique_id)
        groups = Group.query.filter_by(owner_id=current_user.id).all()
        for group in groups:
            # Get unique_id using helper function (handles migration period)
            group_unique_id = _get_unique_id('groups', group.id)
            
            user_data['groups'].append({
                'unique_id': group_unique_id,
                'name': group.name,
                'description': group.description or '',
                'settings': group.settings or {},
                'members': [
                    {
                        'username': member.user.username,
                        'email': member.user.email,
                        'role': member.role,
                        'permissions': member.permissions or {}
                    }
                    for member in group.members
                ]
            })

        # Collect lists (with unique_id and linked to group unique_id)
        lists = List.query.filter_by(user_id=current_user.id).all()
        for lst in lists:
            # Get group unique_id if list belongs to a group
            group_unique_id = None
            if lst.group_id:
                group_unique_id = _get_unique_id('groups', lst.group_id)
            
            user_data['lists'].append({
                'unique_id': lst.unique_id,
                'name': lst.name,
                'description': lst.description or '',
                'tags': lst.get_tags_list() if hasattr(lst, 'get_tags_list') else [],
                'visibility': lst.visibility,
                'group_unique_id': group_unique_id,
                'item_count': len(lst.items)
            })

        # Collect items (with unique_id and linked to list unique_id)
        items = Item.query.filter(Item.list_id.in_(
            db.session.query(List.id).filter_by(user_id=current_user.id)
        )).all()
        for item in items:
            user_data['items'].append({
                'unique_id': item.unique_id,
                'list_unique_id': item.list.unique_id,
                'name': item.name,
                'description': item.description or '',
                'notes': item.notes or '',
                'tags': item.get_tags_list(),
                'item_type': item.item_type.name if item.item_type else None,
                'location': item.location or '',
                'quantity': item.quantity,
                'barcode': item.barcode or '',
                'low_stock_threshold': item.low_stock_threshold or 0,
                'url': item.url or '',
                'reminder_at': item.reminder_at.isoformat() if item.reminder_at else None
            })

        # Collect list shares (with unique_ids instead of database IDs)
        shares = ListShare.query.filter_by(user_id=current_user.id).all()
        for share in shares:
            user_data['list_shares'].append({
                'list_unique_id': share.list.unique_id,
                'list_name': share.list.name,
                'permission': share.permission,
                'shared_by_username': share.shared_by.username
            })

        # Commit any newly generated unique_ids
        db.session.commit()

        # Create JSON response
        json_data = json.dumps(user_data, indent=2)

        # Return as downloadable file
        from flask import send_file
        response = send_file(
            BytesIO(json_data.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'thinglist_export_{current_user.username}_{datetime.datetime.utcnow().strftime("%Y%m%d")}.json'
        )

        # Log the data export action
        _log_action('export', 'account_data', current_user.id, {})

        return response
    except Exception as e:
        app.logger.error(f'Data export error: {str(e)}')
        flash('An error occurred while exporting your data.', 'error')
        return redirect(url_for('profile'))


@app.route('/user/clear-all-data', methods=['GET', 'POST'])
@login_required
def clear_all_user_data():
    """Clear all user data but keep the account (unlike delete_account which deletes everything)"""
    if request.method == 'GET':
        # Show confirmation page with data summary
        user_lists_count = List.query.filter_by(user_id=current_user.id).count()
        user_items_count = Item.query.filter(Item.list_id.in_(
            db.session.query(List.id).filter_by(user_id=current_user.id)
        )).count()
        user_groups_count = Group.query.filter_by(owner_id=current_user.id).count()

        return render_template(
            'gdpr/clear_all_data.html',
            lists_count=user_lists_count,
            items_count=user_items_count,
            groups_count=user_groups_count
        )

    elif request.method == 'POST':
        try:
            # Verify password for security
            password = request.form.get('password', '').strip()
            if not current_user.check_password(password):
                flash('Incorrect password. Data clear cancelled.', 'error')
                return redirect(url_for('clear_all_user_data'))

            user_id = current_user.id
            username = current_user.username

            # Delete all user data in proper order (respecting FK constraints)
            # DO NOT delete the user account itself
            
            # 1. Delete notifications
            Notification.query.filter_by(user_id=user_id).delete()

            # 2. Delete audit logs
            AuditLog.query.filter_by(user_id=user_id).delete()

            # 3. Delete list shares involving this user
            ListShare.query.filter(
                (ListShare.user_id == user_id) | (ListShare.shared_by_id == user_id)
            ).delete()

            # 4. Delete group memberships
            GroupMember.query.filter_by(user_id=user_id).delete()

            # 5. Delete items in user's lists (and all their relationships)
            user_list_ids = db.session.query(List.id).filter_by(user_id=user_id).all()
            user_list_ids_flat = [list_id[0] for list_id in user_list_ids]
            
            if user_list_ids_flat:
                # Delete all items that belong to user's lists
                items_result = db.session.query(Item.id).filter(
                    Item.list_id.in_(user_list_ids_flat)
                ).all()
                item_ids_flat = [item_id[0] for item_id in items_result]
                
                if item_ids_flat:
                    # Delete item relationships in order (respecting FK constraints)
                    ItemImage.query.filter(ItemImage.item_id.in_(item_ids_flat)).delete()
                    ItemAttachment.query.filter(ItemAttachment.item_id.in_(item_ids_flat)).delete()
                    ItemCustomField.query.filter(ItemCustomField.item_id.in_(item_ids_flat)).delete()
                    # Now delete the items themselves
                    Item.query.filter(Item.id.in_(item_ids_flat)).delete()

            # 6. Delete custom fields in user's lists
            ListCustomField.query.filter(
                ListCustomField.list_id.in_(db.session.query(List.id).filter_by(user_id=user_id))
            ).delete()

            # 7. Delete lists
            List.query.filter_by(user_id=user_id).delete()

            # 8. Delete groups owned by user
            Group.query.filter_by(owner_id=user_id).delete()

            # 9. Delete item types created by user
            ItemType.query.filter_by(user_id=user_id).delete()

            # 10. Delete tags created by user
            Tag.query.filter_by(user_id=user_id).delete()

            # NOTE: User account is NOT deleted - it remains active

            db.session.commit()

            # Log action
            app.logger.info(f'User data cleared for: {username} (ID: {user_id})')
            _log_action('clear_data', 'all_user_data', user_id, {})

            flash(
                'All your data has been permanently deleted. Your account remains active.',
                'success'
            )
            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Data clear error for user {current_user.id}: {str(e)}')
            flash('An error occurred while clearing your data. Please try again.', 'error')
            return redirect(url_for('clear_all_user_data'))


@app.route('/gdpr/delete-account', methods=['GET', 'POST'])
@login_required
def delete_account():
    """Delete user account and all associated data (GDPR right to erasure)"""
    if request.method == 'GET':
        # Show confirmation page with data export offer
        user_lists_count = List.query.filter_by(user_id=current_user.id).count()
        user_items_count = Item.query.filter(Item.list_id.in_(
            db.session.query(List.id).filter_by(user_id=current_user.id)
        )).count()
        user_groups_count = Group.query.filter_by(owner_id=current_user.id).count()

        return render_template(
            'gdpr/delete_account.html',
            lists_count=user_lists_count,
            items_count=user_items_count,
            groups_count=user_groups_count
        )

    elif request.method == 'POST':
        try:
            # Verify password for security
            password = request.form.get('password', '').strip()
            if not current_user.check_password(password):
                flash('Incorrect password. Account deletion cancelled.', 'error')
                return redirect(url_for('delete_account'))

            user_id = current_user.id
            username = current_user.username

            # Delete all user data in proper order (respecting FK constraints)
            # 1. Delete notifications
            Notification.query.filter_by(user_id=user_id).delete()

            # 2. Delete audit logs
            AuditLog.query.filter_by(user_id=user_id).delete()

            # 3. Delete list shares involving this user
            ListShare.query.filter(
                (ListShare.user_id == user_id) | (ListShare.shared_by_id == user_id)
            ).delete()

            # 4. Delete group memberships
            GroupMember.query.filter_by(user_id=user_id).delete()

            # 5. Delete items in user's lists (and all their relationships)
            user_list_ids = db.session.query(List.id).filter_by(user_id=user_id).all()
            user_list_ids_flat = [list_id[0] for list_id in user_list_ids]
            
            if user_list_ids_flat:
                # Delete all items that belong to user's lists
                items_result = db.session.query(Item.id).filter(
                    Item.list_id.in_(user_list_ids_flat)
                ).all()
                item_ids_flat = [item_id[0] for item_id in items_result]
                
                if item_ids_flat:
                    # Delete item relationships in order (respecting FK constraints)
                    ItemImage.query.filter(ItemImage.item_id.in_(item_ids_flat)).delete()
                    ItemAttachment.query.filter(ItemAttachment.item_id.in_(item_ids_flat)).delete()
                    ItemCustomField.query.filter(ItemCustomField.item_id.in_(item_ids_flat)).delete()
                    # Now delete the items themselves
                    Item.query.filter(Item.id.in_(item_ids_flat)).delete()

            # 6. Delete custom fields in user's lists
            ListCustomField.query.filter(
                ListCustomField.list_id.in_(db.session.query(List.id).filter_by(user_id=user_id))
            ).delete()

            # 7. Delete lists
            List.query.filter_by(user_id=user_id).delete()

            # 8. Delete groups owned by user
            Group.query.filter_by(owner_id=user_id).delete()

            # 9. Delete item types created by user
            ItemType.query.filter_by(user_id=user_id).delete()

            # 10. Delete tags created by user
            Tag.query.filter_by(user_id=user_id).delete()

            # 11. Delete the user account
            User.query.filter_by(id=user_id).delete()

            db.session.commit()

            # Log action (before logout)
            app.logger.info(f'User account deleted: {username} (ID: {user_id})')

            # Clear session and logout
            logout_user()

            flash(
                'Your account and all associated data have been permanently deleted. '
                'Thank you for using ThingList.',
                'success'
            )
            return redirect(url_for('index'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Account deletion error for user {current_user.id}: {str(e)}')
            flash('An error occurred while deleting your account. Please try again.', 'error')
            return redirect(url_for('delete_account'))


@app.route('/privacy-policy')
def privacy_policy():
    """GDPR Privacy Policy page"""
    return render_template('gdpr/privacy_policy.html')


@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template('gdpr/terms_of_service.html')


@app.route('/gdpr/data-processing')
def data_processing():
    """Data Processing & GDPR Compliance information"""
    return render_template('gdpr/data_processing.html')


# ============================================================================
# PHASE 2: ACCOUNT-LEVEL DATA EXPORT AND IMPORT
# ============================================================================

@app.route('/user/data-management')
@login_required
def data_management():
    """Display data management and export/import options"""
    return render_template('data_management.html')


@app.route('/user/export-all-data', methods=['GET'])
@login_required
@limiter.limit("5 per minute")
def export_all_user_data():
    """Export all user data including groups, lists, items, and shares
    Uses unique_id instead of database IDs for portability"""
    try:
        from io import BytesIO
        
        export_data = {
            'version': '1.0',
            'export_type': 'full_account_export',
            'username': current_user.username,
            'email': current_user.email,
            'preferences': current_user.preferences or {},
            'groups': [],
            'lists': [],
            'items': [],
            'list_shares': [],
        }

        # Export all groups owned by user
        groups = Group.query.filter_by(owner_id=current_user.id).all()
        for group in groups:
            # Get unique_id using helper function (handles migration period)
            group_unique_id = _get_unique_id('groups', group.id)
            
            export_data['groups'].append({
                'unique_id': group_unique_id,
                'name': group.name,
                'description': group.description or '',
                'settings': group.settings or {},
                'members': [
                    {
                        'username': member.user.username,
                        'email': member.user.email,
                        'role': member.role,
                        'permissions': member.permissions or {}
                    }
                    for member in group.members
                ]
            })

        # Export all lists owned by user
        lists = List.query.filter_by(user_id=current_user.id).all()
        for lst in lists:
            # Get group unique_id if list belongs to a group
            group_unique_id = None
            if lst.group_id:
                group_unique_id = _get_unique_id('groups', lst.group_id)
            
            export_data['lists'].append({
                'unique_id': lst.unique_id,
                'name': lst.name,
                'description': lst.description or '',
                'tags': lst.get_tags_list() if hasattr(lst, 'get_tags_list') else [],
                'visibility': lst.visibility,
                'group_unique_id': group_unique_id,
                'item_count': len(lst.items)
            })

        # Export all items in user's lists
        items = Item.query.filter(Item.list_id.in_(
            db.session.query(List.id).filter_by(user_id=current_user.id)
        )).all()
        for item in items:
            export_data['items'].append({
                'unique_id': item.unique_id,
                'list_unique_id': item.list.unique_id,
                'name': item.name,
                'description': item.description or '',
                'notes': item.notes or '',
                'tags': item.get_tags_list(),
                'item_type': item.item_type.name if item.item_type else None,
                'location': item.location or '',
                'quantity': item.quantity,
                'barcode': item.barcode or '',
                'low_stock_threshold': item.low_stock_threshold or 0,
                'url': item.url or '',
                'reminder_at': item.reminder_at.isoformat() if item.reminder_at else None
            })

        # Export list shares (lists shared with this user by others)
        shares = ListShare.query.filter_by(user_id=current_user.id).all()
        for share in shares:
            export_data['list_shares'].append({
                'list_unique_id': share.list.unique_id,
                'list_name': share.list.name,
                'permission': share.permission,
                'shared_by_username': share.shared_by.username
            })

        # Create JSON response
        json_str = json.dumps(export_data, indent=2)

        # Return as downloadable file
        response = send_file(
            BytesIO(json_str.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'thinglist_full_export_{current_user.username}_{datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
        )

        # Log the export action
        _log_action('export', 'full_account_data', current_user.id, {
            'groups': len(groups),
            'lists': len(lists),
            'items': len(items),
            'shares': len(shares)
        })

        return response
    except Exception as e:
        app.logger.error(f'Full data export error for user {current_user.id}: {str(e)}')
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('profile'))


@app.route('/user/import-all-data', methods=['GET', 'POST'])
@login_required
@limiter.limit("5 per minute")
def import_all_user_data():
    """Import all user data from full account export
    Supports conflict resolution for groups, lists, and items"""
    if request.method == 'GET':
        # Show import form
        return render_template('import_all_data.html')

    # POST - Handle the import
    file = request.files.get('import_file')
    group_conflict = request.form.get('group_conflict', 'skip')  # skip, overwrite, or merge
    list_conflict = request.form.get('list_conflict', 'skip')    # skip, overwrite, or create_new
    item_conflict = request.form.get('item_conflict', 'skip')    # skip or overwrite

    if not file or not file.filename:
        flash('Please select a file to import.', 'error')
        return redirect(url_for('import_all_user_data'))

    try:
        content = file.stream.read().decode('utf-8')
        data = json.loads(content)

        # Validate file format
        if data.get('export_type') != 'full_account_export':
            flash('Invalid export file. Please use a file exported from "Export All Data".', 'error')
            return redirect(url_for('import_all_user_data'))

        # Track import statistics
        stats = {
            'groups_imported': 0,
            'groups_skipped': 0,
            'groups_updated': 0,
            'lists_imported': 0,
            'lists_skipped': 0,
            'lists_updated': 0,
            'items_imported': 0,
            'items_skipped': 0,
            'items_updated': 0,
        }

        # Map to track imported unique_ids to new database IDs for linking
        group_id_map = {}  # {old_unique_id: new_group_id}
        list_id_map = {}   # {old_unique_id: new_list_id}

        # ========== IMPORT GROUPS ==========
        for group_data in data.get('groups', []):
            unique_id = group_data.get('unique_id')
            name = group_data.get('name', '').strip()
            
            if not name or not unique_id:
                continue

            # Check if group with this unique_id already exists (using raw SQL)
            try:
                existing_row = db.session.execute(
                    text('SELECT id FROM groups WHERE unique_id = :uid AND owner_id = :oid'),
                    {'uid': unique_id, 'oid': current_user.id}
                ).fetchone()
                existing_group_id = existing_row[0] if existing_row else None
            except:
                existing_group_id = None

            if existing_group_id:
                # Group already exists
                existing_group = Group.query.get(existing_group_id)
                if group_conflict == 'overwrite':
                    # Update existing group
                    existing_group.name = name
                    existing_group.description = group_data.get('description', '')
                    existing_group.settings = group_data.get('settings', {})
                    db.session.add(existing_group)
                    group_id_map[unique_id] = existing_group.id
                    stats['groups_updated'] += 1
                elif group_conflict == 'merge':
                    # Keep existing group, just map it
                    group_id_map[unique_id] = existing_group.id
                    stats['groups_skipped'] += 1
                else:  # skip
                    group_id_map[unique_id] = existing_group.id
                    stats['groups_skipped'] += 1
            else:
                # Create new group
                new_group = Group(
                    name=name,
                    description=group_data.get('description', ''),
                    owner_id=current_user.id,
                    settings=group_data.get('settings', {})
                )
                db.session.add(new_group)
                db.session.flush()  # Get the ID
                
                # Generate slug now that group has an ID
                new_group.generate_slug()
                
                # Store unique_id in database
                db.session.execute(
                    text('UPDATE groups SET unique_id = :uid WHERE id = :gid'),
                    {'uid': unique_id, 'gid': new_group.id}
                )
                
                group_id_map[unique_id] = new_group.id
                stats['groups_imported'] += 1

                # Add group members
                for member_data in group_data.get('members', []):
                    member_username = member_data.get('username')
                    member_role = member_data.get('role', 'member')
                    
                    # Find user by username
                    member_user = User.query.filter_by(username=member_username).first()
                    if member_user:
                        new_member = GroupMember(
                            group_id=new_group.id,
                            user_id=member_user.id,
                            role=member_role,
                            permissions=member_data.get('permissions', {})
                        )
                        db.session.add(new_member)

        # ========== IMPORT LISTS ==========
        for list_data in data.get('lists', []):
            unique_id = list_data.get('unique_id')
            name = list_data.get('name', '').strip()
            group_unique_id = list_data.get('group_unique_id')
            
            if not name or not unique_id:
                continue

            # Check if list with this unique_id already exists
            existing_list = List.query.filter_by(unique_id=unique_id, user_id=current_user.id).first()

            if existing_list:
                # List already exists
                if list_conflict == 'overwrite':
                    # Update existing list
                    existing_list.name = name
                    existing_list.description = list_data.get('description', '')
                    existing_list.visibility = list_data.get('visibility', 'private')
                    if group_unique_id and group_unique_id in group_id_map:
                        existing_list.group_id = group_id_map[group_unique_id]
                    else:
                        existing_list.group_id = None
                    db.session.add(existing_list)
                    list_id_map[unique_id] = existing_list.id
                    stats['lists_updated'] += 1
                else:  # skip or create_new both skip
                    list_id_map[unique_id] = existing_list.id
                    stats['lists_skipped'] += 1
            else:
                # Create new list
                new_list = List(
                    unique_id=unique_id,
                    name=name,
                    description=list_data.get('description', ''),
                    visibility=list_data.get('visibility', 'private'),
                    user_id=current_user.id,
                    group_id=group_id_map.get(group_unique_id) if group_unique_id else None
                )
                db.session.add(new_list)
                db.session.flush()  # Get the ID
                
                # Generate slug now that list has an ID
                new_list.generate_slug()
                
                list_id_map[unique_id] = new_list.id
                
                # Add tags if present
                tags_list = list_data.get('tags', [])
                if tags_list and hasattr(new_list, 'set_tags_list'):
                    new_list.set_tags_list(tags_list)
                
                stats['lists_imported'] += 1

        # ========== IMPORT ITEMS ==========
        for item_data in data.get('items', []):
            unique_id = item_data.get('unique_id')
            name = (item_data.get('name') or '').strip()
            list_unique_id = item_data.get('list_unique_id')
            
            if not name or not unique_id or list_unique_id not in list_id_map:
                continue

            list_id = list_id_map[list_unique_id]

            # Check if item with this unique_id already exists in this list
            existing_item = Item.query.filter_by(unique_id=unique_id, list_id=list_id).first()

            if existing_item:
                # Item already exists
                if item_conflict == 'overwrite':
                    # Update existing item
                    existing_item.name = name
                    existing_item.description = item_data.get('description', '')
                    existing_item.notes = item_data.get('notes', '')
                    existing_item.location = item_data.get('location', '')
                    existing_item.quantity = int(item_data.get('quantity', 1))
                    existing_item.barcode = item_data.get('barcode', '')
                    existing_item.low_stock_threshold = int(item_data.get('low_stock_threshold', 0))
                    existing_item.url = item_data.get('url', '')
                    
                    # Set item type
                    item_type_name = item_data.get('item_type')
                    if item_type_name:
                        existing_item.item_type = ItemType.get_or_create(item_type_name, current_user.id)
                    
                    # Set reminder
                    if item_data.get('reminder_at'):
                        try:
                            existing_item.reminder_at = datetime.datetime.fromisoformat(item_data['reminder_at'])
                        except:
                            existing_item.reminder_at = None
                    
                    db.session.add(existing_item)
                    
                    # Update tags
                    tags_list = item_data.get('tags', [])
                    existing_item.set_tags_list(tags_list)
                    
                    stats['items_updated'] += 1
                else:  # skip
                    stats['items_skipped'] += 1
            else:
                # Create new item
                item_type = None
                item_type_name = item_data.get('item_type')
                if item_type_name:
                    item_type = ItemType.get_or_create(item_type_name, current_user.id)

                new_item = Item(
                    unique_id=unique_id,
                    name=name,
                    description=item_data.get('description', ''),
                    notes=item_data.get('notes', ''),
                    tags=','.join(item_data.get('tags', [])),
                    item_type=item_type,
                    location=item_data.get('location', ''),
                    quantity=int(item_data.get('quantity', 1)),
                    barcode=item_data.get('barcode', ''),
                    low_stock_threshold=int(item_data.get('low_stock_threshold', 0)),
                    url=item_data.get('url', ''),
                    list_id=list_id
                )

                # Set reminder
                if item_data.get('reminder_at'):
                    try:
                        new_item.reminder_at = datetime.datetime.fromisoformat(item_data['reminder_at'])
                    except:
                        new_item.reminder_at = None

                db.session.add(new_item)
                db.session.flush()  # Get the ID
                
                # Set tags
                tags_list = item_data.get('tags', [])
                new_item.set_tags_list(tags_list)
                
                stats['items_imported'] += 1

        db.session.commit()
        _log_action('import', 'full_account_data', current_user.id, stats)

        message = (f'Import complete: '
                   f'{stats["groups_imported"]} groups, '
                   f'{stats["lists_imported"]} lists, '
                   f'{stats["items_imported"]} items imported. '
                   f'{stats["groups_skipped"]} groups, {stats["lists_skipped"]} lists, {stats["items_skipped"]} items skipped.')
        flash(message, 'success')
    except json.JSONDecodeError:
        flash('Invalid JSON file format.', 'error')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Full data import error for user {current_user.id}: {str(e)}')
        flash(f'Import failed: {str(e)}', 'error')

    return redirect(url_for('profile'))
