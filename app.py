from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_from_directory, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text, event
from sqlalchemy.orm import attributes
from models import db, User, List, Item, ItemType, Tag, ItemAttachment, AuditLog, item_tags, ListCustomField, ItemCustomField, ListShare, Notification, ItemImage, Group, GroupMember
from forms import RegistrationForm, LoginForm, CreateGroupForm, EditGroupForm, AddGroupMemberForm, EditGroupMemberForm, ForgotPasswordForm, ResetPasswordForm, PasswordChangeForm
from config import config
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
login_manager.login_view = 'login'
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
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "connect-src 'self'; "
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

# Simple in-memory cache for autocomplete
_autocomplete_cache = {}
_autocomplete_ttl = 30


def _cache_get(key):
    entry = _autocomplete_cache.get(key)
    if not entry:
        return None
    value, timestamp = entry
    if time.time() - timestamp > _autocomplete_ttl:
        _autocomplete_cache.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _autocomplete_cache[key] = (value, time.time())


def _parse_tags(raw_tags):
    return [t.strip() for t in (raw_tags or '').split(',') if t.strip()]


def _log_action(action, entity, entity_id, meta=None):
    try:
        from models import AuditLog
        log = AuditLog(user_id=current_user.id, action=action, entity=entity, entity_id=entity_id, meta=meta)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _save_attachments(item, files):
    from models import ItemAttachment
    if not files:
        return
    for f in files:
        if not f or not f.filename:
            continue
        filename = secure_filename(f.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        f.save(file_path)
        attachment = ItemAttachment(
            item_id=item.id,
            filename=filename,
            file_path=file_path,
            content_type=f.content_type,
            file_size=os.path.getsize(file_path)
        )
        db.session.add(attachment)


def _normalize_image_base_url(base_url):
    if not base_url:
        return '/'
    return base_url if base_url.endswith('/') else f"{base_url}/"


def _allowed_image_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in app.config.get('IMAGE_ALLOWED_EXTENSIONS', set())


def _convert_and_store_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed_image_file(file_storage.filename):
        return None

    output_format = (app.config.get('IMAGE_OUTPUT_FORMAT') or 'webp').lower()
    format_map = {'jpg': 'jpeg'}
    output_format = format_map.get(output_format, output_format)

    unique_name = f"{uuid.uuid4().hex}.{output_format}"
    storage_path = os.path.join(app.config['IMAGE_STORAGE_DIR'], unique_name)
    image_url = f"{_normalize_image_base_url(app.config.get('IMAGE_BASE_URL'))}{unique_name}"

    try:
        image = Image.open(file_storage.stream)
        if output_format in ('jpeg', 'jpg'):
            if image.mode != 'RGB':
                image = image.convert('RGB')
        elif output_format == 'webp':
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA')
        elif image.mode == 'P':
            image = image.convert('RGBA')

        save_kwargs = {}
        if output_format in ('jpeg', 'jpg', 'webp'):
            save_kwargs['quality'] = 85
        image.save(storage_path, output_format.upper(), **save_kwargs)
    except (UnidentifiedImageError, OSError):
        return None

    return ItemImage(
        original_filename=secure_filename(file_storage.filename),
        storage_path=storage_path,
        image_url=image_url,
        content_type=f"image/{'jpeg' if output_format == 'jpg' else output_format}",
        file_size=os.path.getsize(storage_path)
    )


def _save_item_images(item, files):
    if not files:
        return

    created = []
    for f in files:
        image_record = _convert_and_store_image(f)
        if not image_record:
            continue
        image_record.item_id = item.id
        db.session.add(image_record)
        created.append(image_record)

    if not created:
        return

    has_main = ItemImage.query.filter_by(item_id=item.id, is_main=True).first()
    if not has_main:
        created[0].is_main = True


# Initialize database on app startup
with app.app_context():
    try:
        db.create_all()

        # Ensure legacy columns exist
        inspector = inspect(db.engine)
        try:
            item_columns = [col['name'] for col in inspector.get_columns('items')]
        except Exception:
            item_columns = []

        if 'item_type_id' not in item_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN item_type_id INT NULL"))
                try:
                    conn.execute(text("ALTER TABLE items ADD FOREIGN KEY (item_type_id) REFERENCES item_types(id) ON DELETE SET NULL"))
                except Exception:
                    pass
                conn.commit()

        if 'low_stock_threshold' not in item_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN low_stock_threshold INT DEFAULT 0"))
                conn.commit()

        if 'barcode' not in item_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN barcode VARCHAR(128)"))
                conn.commit()

        if 'notes' not in item_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN notes TEXT"))
                conn.commit()

        if 'reminder_at' not in item_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE items ADD COLUMN reminder_at DATETIME"))
                conn.commit()

        # Ensure preferences column exists in users table
        try:
            user_columns = [col['name'] for col in inspector.get_columns('users')]
        except Exception:
            user_columns = []

        if 'preferences' not in user_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN preferences JSON DEFAULT '{}'"))
                conn.commit()
                app.logger.info("Added preferences column to users table")

        # Initialize system item types if they don't exist
        if ItemType.query.filter_by(is_system=True).count() == 0:
            system_types = [
                'Appliance', 'Electronics', 'Furniture', 'Clothing', 'Books',
                'Kitchen', 'Tools', 'Sports', 'Toys', 'Decorations',
                'Office', 'Garden', 'Bedding', 'Dishes', 'Cleaning'
            ]
            for type_name in system_types:
                db.session.add(ItemType(name=type_name, is_system=True, user_id=None))
            db.session.commit()
    except Exception as e:
        app.logger.error(f"Database initialization error: {str(e)}")


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


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            from email_utils import generate_token, send_verification_email

            user = User(
                username=form.username.data,
                email=form.email.data.lower()
            )
            user.set_password(form.password.data)

            # Generate email verification token
            verification_token = generate_token()
            user.set_email_verification_token(verification_token)

            db.session.add(user)
            db.session.commit()

            # Send verification email
            base_url = request.host_url.rstrip('/')
            send_verification_email(user, verification_token, base_url)

            flash('Registration successful! Please check your email to verify your account.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            app.logger.error(f'Registration error: {str(e)}')

    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """User login with username or email"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()

    # Debug CSRF token on GET request
    if request.method == 'GET':
        app.logger.debug(f'LOGIN GET: Session ID present: {bool(request.cookies.get("session"))}')

    # Debug CSRF token on POST request
    if request.method == 'POST':
        app.logger.debug(f'LOGIN POST: Session ID present: {bool(request.cookies.get("session"))}')
        app.logger.debug(f'LOGIN POST: CSRF Token in form: {bool(request.form.get("csrf_token"))}')
        app.logger.debug(f'LOGIN POST: Form validation result: {form.validate_on_submit()}')
        if form.errors:
            app.logger.debug(f'LOGIN POST: Form errors: {form.errors}')

    if form.validate_on_submit():
        # Get user from form validation (already verified)
        credential = form.credential.data.lower().strip()

        # Try to find user by email first, then by username
        user = User.query.filter_by(email=credential).first()
        if not user:
            user = User.query.filter_by(username=credential).first()

        if user and user.check_password(form.password.data):
            # Check if email is verified
            if not user.email_verified:
                flash("Email not verified. Please check your email inbox for the verification link. If you did not receive it, you can resend it using the link below.", 'warning')
                return redirect(url_for('login'))

            login_user(user, remember=request.form.get('remember') == 'on')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials. Please try again.', 'error')

    return render_template('login.html', form=form)


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


# ============= List Management Routes =============

@app.route('/lists')
@login_required
def lists():
    """View all user's lists (owned and shared)"""
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 5), 100)

    # Get owned lists - but exclude group lists (group_id is NULL means personal list)
    owned_lists_query = List.query.filter_by(user_id=current_user.id, group_id=None).order_by(List.created_at.desc())

    # Get shared lists (via ListShare)
    from sqlalchemy import and_
    shared_lists_query = List.query.join(ListShare, ListShare.list_id == List.id).filter(
        ListShare.user_id == current_user.id
    ).order_by(List.created_at.desc())

    # Combine queries - get unique lists
    all_list_ids = set()
    owned_lists = owned_lists_query.all()
    shared_lists = shared_lists_query.all()

    # Create a combined list with deduplication
    combined_lists = {}
    for lst in owned_lists:
        combined_lists[lst.id] = {'list': lst, 'type': 'owned', 'permission': 'owner'}

    for lst in shared_lists:
        if lst.id not in combined_lists:
            # Get the share info to show permission
            share = ListShare.query.filter_by(list_id=lst.id, user_id=current_user.id).first()
            combined_lists[lst.id] = {
                'list': lst,
                'type': 'shared',
                'permission': share.permission if share else 'view'
            }

    # Sort by creation date (newest first)
    sorted_items = sorted(combined_lists.items(), key=lambda x: x[1]['list'].created_at, reverse=True)

    # Apply pagination
    total = len(sorted_items)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = sorted_items[start:end]

    # Extract just the data for template
    user_lists = [item[1] for item in paginated_items]
    pages = (total + per_page - 1) // per_page if total else 1

    return render_template('lists.html', lists=user_lists, total=total, page=page, pages=pages, per_page=per_page)


@app.route('/public-lists')
def public_lists():
    """Browse public lists"""
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 5), 100)
    search_q = request.args.get('q', '').strip()

    # Get public lists (not owned by current user if authenticated)
    public_lists_query = List.query.filter(
        List.visibility == 'public'
    ).order_by(List.created_at.desc())

    # Filter by search query if provided
    if search_q:
        public_lists_query = public_lists_query.filter(
            List.name.ilike(f'%{search_q}%')
        )

    # Apply pagination
    total = public_lists_query.count()
    start = (page - 1) * per_page
    end = start + per_page
    paginated_lists = public_lists_query.offset(start).limit(per_page).all()

    pages = (total + per_page - 1) // per_page if total else 1

    return render_template(
        'public_lists.html',
        lists=paginated_lists,
        total=total,
        page=page,
        pages=pages,
        per_page=per_page,
        search_q=search_q
    )


@app.route('/lists/create', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
@login_required
def create_list():
    """Create a new list"""
    group_id = request.args.get('group_id', type=int)
    group = None

    if group_id:
        group = Group.query.get_or_404(group_id)
        # Check if user has permission to create lists in this group
        if not group.is_admin(current_user.id) and not group.is_owner(current_user.id):
            # Check if members can create lists
            if not group.get_settings().get('allow_members_create_lists', True):
                flash('You do not have permission to create lists in this group.', 'danger')
                return redirect(url_for('view_group', group_id=group_id))

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            tags = request.form.get('tags', '').strip()
            visibility = request.form.get('visibility', 'private').strip()
            group_id_form = request.form.get('group_id', type=int)

            # Validate visibility value
            if visibility not in ('private', 'public', 'hidden'):
                visibility = 'private'

            if not name:
                flash('List name is required.', 'error')
                return redirect(url_for('create_list', group_id=group_id_form))

            # If group_id provided, verify user has access
            if group_id_form:
                group_check = Group.query.get(group_id_form)
                if not group_check or (not group_check.is_admin(current_user.id) and not group_check.is_owner(current_user.id)):
                    if group_check and not group_check.get_settings().get('allow_members_create_lists', True):
                        flash('You do not have permission to create lists in this group.', 'danger')
                        return redirect(url_for('view_group', group_id=group_id_form))

            new_list = List(
                name=name,
                description=description,
                tags=tags,
                visibility=visibility,
                user_id=group.owner_id if group_id_form and group else current_user.id,
                group_id=group_id_form
            )
            db.session.add(new_list)
            db.session.flush()
            new_list.set_tags_list(_parse_tags(tags))
            db.session.commit()

            _log_action('create', 'list', new_list.id, {'name': name, 'visibility': visibility, 'group_id': group_id_form})
            flash(f'List "{name}" created successfully!', 'success')
            return redirect(url_for('view_list', list_id=new_list.id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the list.', 'error')
            app.logger.error(f'Create list error: {str(e)}')

    return render_template('create_list.html', group=group)


@app.route('/lists/<int:list_id>')
def view_list(list_id):
    """View a specific list and its items"""
    user_list = List.query.get_or_404(list_id)

    # Check access permissions
    if current_user.is_authenticated:
        # Logged in user - check normal permissions
        if not user_list.user_can_access(current_user.id):
            flash('You do not have permission to view this list.', 'error')
            return redirect(url_for('lists'))
        can_edit = user_list.user_can_edit(current_user.id)
    else:
        # Not logged in - only allow public/hidden lists
        if not user_list.is_publicly_accessible():
            flash('You must log in to view this list.', 'info')
            return redirect(url_for('login', next=request.url))
        can_edit = False

    # Filters and pagination
    page = max(int(request.args.get('page', 1)), 1)

    # Get per_page from URL parameter or default
    url_per_page = request.args.get('per_page', None)
    if url_per_page:
        per_page = min(max(int(url_per_page), 5), 100)
    else:
        # For anonymous users, default to 20
        # For authenticated users, use their preference
        if current_user.is_authenticated:
            per_page = current_user.get_items_per_page()
        else:
            per_page = 20

    base_query = _build_item_query(list_id, request.args)
    total = base_query.count()
    items = (base_query
             .order_by(Item.created_at.desc())
             .offset((page - 1) * per_page)
             .limit(per_page)
             .all())

    pages = (total + per_page - 1) // per_page if total else 1

    # Lists for bulk move action (only owned lists or lists user can edit)
    # Only query user lists if user is authenticated
    user_lists = []
    if current_user.is_authenticated:
        user_lists = List.query.filter_by(user_id=current_user.id, group_id=None).order_by(List.created_at.desc()).all()

    return render_template(
        'view_list.html',
        list=user_list,
        items=items,
        total=total,
        page=page,
        pages=pages,
        per_page=per_page,
        user_lists=user_lists,
        can_edit=can_edit,
        filters={
            'q': request.args.get('q', ''),
            'tag': request.args.get('tag', ''),
            'type': request.args.get('type', ''),
            'location': request.args.get('location', ''),
            'low_stock': request.args.get('low_stock', '')
        }
    )


@app.route('/lists/<int:list_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_list(list_id):
    """Edit a list"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    if request.method == 'POST':
        try:
            user_list.name = request.form.get('name', '').strip()
            user_list.description = request.form.get('description', '').strip()
            user_list.tags = request.form.get('tags', '').strip()
            visibility = request.form.get('visibility', 'private').strip()

            # Validate visibility value
            if visibility not in ('private', 'public', 'hidden'):
                visibility = user_list.visibility or 'private'

            user_list.visibility = visibility
            user_list.set_tags_list(_parse_tags(user_list.tags))

            if not user_list.name:
                flash('List name is required.', 'error')
                return redirect(url_for('edit_list', list_id=list_id))

            db.session.commit()
            _log_action('update', 'list', user_list.id, {'name': user_list.name, 'visibility': visibility})
            flash('List updated successfully!', 'success')
            return redirect(url_for('view_list', list_id=list_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the list.', 'error')
            app.logger.error(f'Edit list error: {str(e)}')

    return render_template('edit_list.html', list=user_list)


@app.route('/lists/<int:list_id>/delete', methods=['POST'])
@login_required
def delete_list(list_id):
    """Delete a list"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to delete this list.', 'error')
        return redirect(url_for('lists'))

    try:
        list_name = user_list.name

        # Get all items in the list
        items = Item.query.filter_by(list_id=list_id).all()

        # Delete all item-related data before deleting items
        for item in items:
            # Delete item tags (junction table entries)
            item.tags_rel.clear()

            # Delete item attachments
            ItemAttachment.query.filter_by(item_id=item.id).delete()

            # Delete item images
            ItemImage.query.filter_by(item_id=item.id).delete()

            # Delete item custom fields
            ItemCustomField.query.filter_by(item_id=item.id).delete()

        # Now delete all items in the list
        Item.query.filter_by(list_id=list_id).delete()

        # Delete all list shares
        ListShare.query.filter_by(list_id=list_id).delete()

        # Delete all custom fields in the list
        ListCustomField.query.filter_by(list_id=list_id).delete()

        # Now delete the list itself
        db.session.delete(user_list)
        db.session.commit()

        _log_action('delete', 'list', list_id, {'name': list_name})
        flash(f'List "{list_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the list.', 'error')
        app.logger.error(f'Delete list error: {str(e)}')

    return redirect(url_for('lists'))


@app.route('/lists/<int:list_id>/settings', methods=['GET', 'POST'])
@login_required
def list_settings(list_id):
    """Configure list field visibility and editability settings"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    if request.method == 'POST':
        try:
            # Log the incoming form data
            app.logger.info(f'Form data received: {dict(request.form)}')

            # Define all available fields
            fields = [
                'name', 'description', 'notes', 'quantity', 'low_stock_threshold',
                'item_type', 'location', 'barcode', 'url', 'tags', 'reminder_at', 'attachments', 'images'
            ]
            
            # Build field settings from form data
            field_settings = {}
            for field in fields:
                visible_key = f'visible_{field}'
                editable_key = f'editable_{field}'
                
                # Name is always visible and editable (required field)
                if field == 'name':
                    field_settings[field] = {'visible': True, 'editable': True}
                else:
                    visible = visible_key in request.form
                    editable = editable_key in request.form
                    
                    # If not visible, it can't be editable
                    if not visible:
                        editable = False
                    
                    field_settings[field] = {
                        'visible': visible,
                        'editable': editable
                    }
                    app.logger.debug(f'Field {field}: visible={visible}, editable={editable}')

            # Log the settings being saved
            app.logger.info(f'Saving field settings for list {list_id}: {field_settings}')

            # Save settings
            user_list.set_field_settings(field_settings)
            app.logger.info(f'Settings object after set_field_settings: {user_list.settings}')

            # Mark the settings column as modified so SQLAlchemy detects the change
            attributes.flag_modified(user_list, 'settings')

            db.session.commit()
            app.logger.info(f'Settings saved successfully to database')

            _log_action('update_settings', 'list', user_list.id, {'settings': field_settings})
            flash('List settings updated successfully!', 'success')
            return redirect(url_for('view_list', list_id=list_id))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating settings.', 'error')
            app.logger.error(f'Update list settings error: {str(e)}')

    # Get current field settings
    field_settings = user_list.get_field_settings()
    
    return render_template('list_settings.html', list=user_list, field_settings=field_settings)


@app.route('/lists/<int:list_id>/share', methods=['GET', 'POST'])
@login_required
def share_list(list_id):
    """Manage list sharing with other users"""
    user_list = List.query.get_or_404(list_id)

    # Only owner can share
    if user_list.user_id != current_user.id:
        flash('You do not have permission to share this list.', 'error')
        return redirect(url_for('lists'))

    if request.method == 'POST':
        try:
            action = request.form.get('action')

            if action == 'add':
                username = request.form.get('username', '').strip()
                permission = request.form.get('permission', 'view')

                if not username:
                    flash('Please enter a username.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                # Find user by username
                share_user = User.query.filter_by(username=username).first()
                if not share_user:
                    flash(f'User "{username}" not found.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                # Can't share with self
                if share_user.id == current_user.id:
                    flash('You cannot share a list with yourself.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                # Check if already shared
                existing = ListShare.query.filter_by(list_id=list_id, user_id=share_user.id).first()
                if existing:
                    flash(f'This list is already shared with {username}.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                # Validate permission
                if permission not in ('view', 'edit'):
                    permission = 'view'

                # Create share
                share = ListShare(
                    list_id=list_id,
                    user_id=share_user.id,
                    permission=permission,
                    shared_by_id=current_user.id
                )
                db.session.add(share)
                db.session.commit()

                # Create notification for shared user
                notification = Notification(
                    user_id=share_user.id,
                    notification_type='share',
                    message=f'{current_user.username} shared the list "{user_list.name}" with you ({permission} permission)',
                    list_id=list_id,
                    shared_by_username=current_user.username,
                    permission_level=permission
                )
                db.session.add(notification)
                db.session.commit()

                _log_action('share', 'list', list_id, {
                    'shared_with': username,
                    'permission': permission
                })
                flash(f'List shared with {username} ({permission} permission)!', 'success')
                return redirect(url_for('share_list', list_id=list_id))

            elif action == 'remove':
                user_id = request.form.get('user_id')
                if not user_id or not user_id.isdigit():
                    flash('Invalid user.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                user_id = int(user_id)
                share = ListShare.query.filter_by(list_id=list_id, user_id=user_id).first()
                if not share:
                    flash('Share not found.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                removed_username = share.user.username
                removed_user_id = share.user_id

                db.session.delete(share)
                db.session.commit()

                # Create notification for removed user
                notification = Notification(
                    user_id=removed_user_id,
                    notification_type='unshare',
                    message=f'{current_user.username} revoked your access to the list "{user_list.name}"',
                    list_id=list_id,
                    shared_by_username=current_user.username
                )
                db.session.add(notification)
                db.session.commit()

                _log_action('unshare', 'list', list_id, {'removed_user': removed_username})
                flash(f'Revoked access for {removed_username}.', 'success')
                return redirect(url_for('share_list', list_id=list_id))

            elif action == 'update_permission':
                user_id = request.form.get('user_id')
                permission = request.form.get('permission', 'view')

                if not user_id or not user_id.isdigit():
                    flash('Invalid user.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                if permission not in ('view', 'edit'):
                    permission = 'view'

                user_id = int(user_id)
                share = ListShare.query.filter_by(list_id=list_id, user_id=user_id).first()
                if not share:
                    flash('Share not found.', 'error')
                    return redirect(url_for('share_list', list_id=list_id))

                old_permission = share.permission
                share.permission = permission
                db.session.commit()

                # Create notification for permission change
                if old_permission != permission:
                    notification = Notification(
                        user_id=user_id,
                        notification_type='permission_change',
                        message=f'{current_user.username} changed your permission on "{user_list.name}" from {old_permission} to {permission}',
                        list_id=list_id,
                        shared_by_username=current_user.username,
                        permission_level=permission
                    )
                    db.session.add(notification)
                    db.session.commit()

                _log_action('update_share', 'list', list_id, {
                    'user': share.user.username,
                    'permission': permission
                })
                flash(f'Updated permissions for {share.user.username}.', 'success')
                return redirect(url_for('share_list', list_id=list_id))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while managing shares.', 'error')
            app.logger.error(f'Share list error: {str(e)}')
            return redirect(url_for('share_list', list_id=list_id))

    # Get shared users
    shared_users = user_list.get_shared_users()

    return render_template('share_list.html', list=user_list, shared_users=shared_users)


# ============================================================================
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

        # Owner is automatically an admin
        group.add_member(current_user.id, role='admin')
        db.session.commit()

        flash(f'Group "{group.name}" created successfully!', 'success')
        return redirect(url_for('view_group', group_id=group.id))

    return render_template('groups/create.html', form=form)


@app.route('/groups/<int:group_id>')
@login_required
def view_group(group_id):
    """View group details and members"""
    group = Group.query.get_or_404(group_id)

    # Check if user has access to this group
    if not group.is_owner(current_user.id) and not group.get_member(current_user.id):
        flash('You do not have access to this group.', 'danger')
        return redirect(url_for('view_groups'))

    members = group.get_members()
    lists = List.query.filter_by(group_id=group_id).order_by(List.created_at.desc()).all()

    return render_template(
        'groups/view.html',
        group=group,
        members=members,
        lists=lists,
        is_owner=group.is_owner(current_user.id),
        is_admin=group.is_admin(current_user.id)
    )


@app.route('/groups/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    """Edit group settings (admin only)"""
    group = Group.query.get_or_404(group_id)

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


@app.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Delete a group (owner only)"""
    group = Group.query.get_or_404(group_id)

    # Only owner can delete
    if not group.is_owner(current_user.id):
        flash('You do not have permission to delete this group.', 'danger')
        return redirect(url_for('view_group', group_id=group_id))

    group_name = group.name
    db.session.delete(group)
    db.session.commit()

    flash(f'Group "{group_name}" deleted successfully!', 'success')
    return redirect(url_for('view_groups'))


@app.route('/groups/<int:group_id>/members/add', methods=['GET', 'POST'])
@login_required
def add_group_member(group_id):
    """Add a member to the group (admin only)"""
    group = Group.query.get_or_404(group_id)

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


@app.route('/groups/<int:group_id>/members/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group_member(group_id, user_id):
    """Edit a group member's role and permissions (admin only)"""
    group = Group.query.get_or_404(group_id)

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


@app.route('/groups/<int:group_id>/members/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_group_member(group_id, user_id):
    """Remove a member from the group (admin only)"""
    group = Group.query.get_or_404(group_id)

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


@app.route('/lists/<int:list_id>/custom-fields/add', methods=['POST'])
@login_required
def add_custom_field(list_id):
    """Add a custom field to a list"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    try:
        name = request.form.get('field_name', '').strip()
        field_type = request.form.get('field_type', 'text')

        if not name:
            flash('Field name is required.', 'error')
            return redirect(url_for('list_settings', list_id=list_id))

        # Check if field already exists
        existing = ListCustomField.query.filter_by(list_id=list_id, name=name).first()
        if existing:
            flash('A field with this name already exists.', 'error')
            return redirect(url_for('list_settings', list_id=list_id))

        # Parse options for option field type
        options = None
        if field_type == 'options':
            options_str = request.form.get('field_options', '').strip()
            if options_str:
                options = [opt.strip() for opt in options_str.split('\n') if opt.strip()]
            else:
                flash('Options are required for option fields.', 'error')
                return redirect(url_for('list_settings', list_id=list_id))

        # Get highest sort order
        max_sort = db.session.query(db.func.max(ListCustomField.sort_order)).filter_by(list_id=list_id).scalar() or 0

        new_field = ListCustomField(
            list_id=list_id,
            name=name,
            field_type=field_type,
            options=options,
            sort_order=max_sort + 1,
            is_visible=True,
            is_editable=True
        )

        db.session.add(new_field)
        db.session.commit()

        _log_action('create', 'custom_field', new_field.id, {'name': name, 'type': field_type})
        flash(f'Custom field "{name}" added successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred while adding the field.', 'error')
        app.logger.error(f'Add custom field error: {str(e)}')

    return redirect(url_for('list_settings', list_id=list_id))


@app.route('/lists/<int:list_id>/custom-fields/<int:field_id>/delete', methods=['POST'])
@login_required
def delete_custom_field(list_id, field_id):
    """Delete a custom field from a list"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    try:
        field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()
        field_name = field.name

        # Delete all item custom field values that reference this field
        ItemCustomField.query.filter_by(field_id=field_id).delete()

        # Delete the field
        db.session.delete(field)
        db.session.commit()

        _log_action('delete', 'custom_field', field_id, {'name': field_name})
        flash(f'Custom field "{field_name}" deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the field.', 'error')
        app.logger.error(f'Delete custom field error: {str(e)}')

    return redirect(url_for('list_settings', list_id=list_id))


@app.route('/lists/<int:list_id>/custom-fields/<int:field_id>/toggle-visibility', methods=['POST'])
@login_required
def toggle_custom_field_visibility(list_id, field_id):
    """Toggle visibility of a custom field"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    try:
        field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()
        field.is_visible = not field.is_visible
        db.session.commit()

        status = 'visible' if field.is_visible else 'hidden'
        flash(f'Field "{field.name}" is now {status}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred.', 'error')
        app.logger.error(f'Toggle visibility error: {str(e)}')

    return redirect(url_for('list_settings', list_id=list_id))


@app.route('/lists/<int:list_id>/custom-fields/<int:field_id>/toggle-editable', methods=['POST'])
@login_required
def toggle_custom_field_editable(list_id, field_id):
    """Toggle editability of a custom field"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    try:
        field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()
        field.is_editable = not field.is_editable
        db.session.commit()

        status = 'editable' if field.is_editable else 'read-only'
        flash(f'Field "{field.name}" is now {status}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred.', 'error')
        app.logger.error(f'Toggle editable error: {str(e)}')

    return redirect(url_for('list_settings', list_id=list_id))


@app.route('/lists/<int:list_id>/custom-fields/<int:field_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_custom_field_name(list_id, field_id):
    """Edit a custom field name"""
    user_list = List.query.get_or_404(list_id)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('lists'))

    field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()

    if request.method == 'POST':
        try:
            new_name = request.form.get('field_name', '').strip()

            if not new_name:
                flash('Field name cannot be empty.', 'error')
                return redirect(url_for('list_settings', list_id=list_id))

            # Check if the new name already exists (excluding the current field)
            existing = ListCustomField.query.filter_by(list_id=list_id, name=new_name).filter(
                ListCustomField.id != field_id
            ).first()

            if existing:
                flash(f'A field named "{new_name}" already exists in this list.', 'error')
                return redirect(url_for('list_settings', list_id=list_id))

            old_name = field.name
            field.name = new_name
            db.session.commit()

            _log_action('edit', 'custom_field', field_id, {
                'old_name': old_name,
                'new_name': new_name
            })
            flash(f'Custom field renamed from "{old_name}" to "{new_name}".', 'success')

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while editing the field.', 'error')
            app.logger.error(f'Edit custom field name error: {str(e)}')

        return redirect(url_for('list_settings', list_id=list_id))

    # GET request - show edit form
    return render_template('edit_custom_field.html', list=user_list, field=field)


@app.route('/lists/<int:list_id>/items/create', methods=['GET', 'POST'])
@limiter.limit("60 per minute")
@login_required
def create_item(list_id):
    """Create a new item in a list"""
    user_list = List.query.get_or_404(list_id)

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to add items to this list.', 'error')
        return redirect(url_for('lists'))

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            notes = request.form.get('notes', '').strip()
            tags = request.form.get('tags', '').strip()
            item_type_name = request.form.get('item_type', '').strip()
            location = request.form.get('location', '').strip()
            quantity = request.form.get('quantity', '1')
            url = request.form.get('url', '').strip()
            barcode = request.form.get('barcode', '').strip()
            low_stock_threshold = request.form.get('low_stock_threshold', '0')
            reminder_at_raw = request.form.get('reminder_at', '').strip()

            if not name:
                flash('Item name is required.', 'error')
                return redirect(url_for('create_item', list_id=list_id))

            try:
                quantity = int(quantity) if quantity else 1
            except ValueError:
                quantity = 1

            try:
                low_stock_threshold = int(low_stock_threshold) if low_stock_threshold else 0
            except ValueError:
                low_stock_threshold = 0

            # Parse reminder_at as ISO format date
            reminder_at = None
            if reminder_at_raw:
                try:
                    reminder_at = datetime.datetime.fromisoformat(reminder_at_raw)
                except ValueError:
                    reminder_at = None

            # Get or create item type
            item_type = None
            if item_type_name:
                item_type = ItemType.get_or_create(item_type_name, current_user.id)

            new_item = Item(
                name=name,
                description=description,
                notes=notes,
                tags=tags,
                item_type=item_type,
                location=location,
                quantity=quantity,
                url=url,
                barcode=barcode,
                low_stock_threshold=low_stock_threshold,
                reminder_at=reminder_at,
                list_id=list_id
            )
            db.session.add(new_item)
            db.session.flush()
            new_item.set_tags_list(_parse_tags(tags))
            _save_attachments(new_item, request.files.getlist('attachments'))
            _save_item_images(new_item, request.files.getlist('images'))

            # Handle custom fields
            for field in user_list.get_custom_fields():
                custom_value = request.form.get(f'custom_{field.id}', '').strip()

                if field.field_type == 'text':
                    if custom_value:
                        custom_field = ItemCustomField(
                            item_id=new_item.id,
                            field_id=field.id,
                            value_text=custom_value
                        )
                        db.session.add(custom_field)

                elif field.field_type == 'boolean':
                    # Checkbox only present if checked
                    is_checked = f'custom_{field.id}' in request.form
                    if is_checked:
                        custom_field = ItemCustomField(
                            item_id=new_item.id,
                            field_id=field.id,
                            value_bool=True
                        )
                        db.session.add(custom_field)

                elif field.field_type == 'options':
                    if custom_value:
                        custom_field = ItemCustomField(
                            item_id=new_item.id,
                            field_id=field.id,
                            value_option=custom_value
                        )
                        db.session.add(custom_field)

            db.session.commit()

            _log_action('create', 'item', new_item.id, {'name': name, 'list_id': list_id})
            flash(f'Item "{name}" added successfully!', 'success')
            return redirect(url_for('view_list', list_id=list_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the item.', 'error')
            app.logger.error(f'Create item error: {str(e)}')

    return render_template('create_item.html', list=user_list)


@app.route('/items/<int:item_id>')
def view_item(item_id):
    """View item details"""
    item = Item.query.get_or_404(item_id)
    user_list = item.list

    # Check access permissions
    if current_user.is_authenticated:
        # Logged in user - check normal permissions
        if not user_list.user_can_access(current_user.id):
            flash('You do not have permission to view this item.', 'error')
            return redirect(url_for('lists'))
        can_edit = user_list.user_can_edit(current_user.id)
    else:
        # Not logged in - only allow public/hidden lists
        if not user_list.is_publicly_accessible():
            flash('You must log in to view this item.', 'info')
            return redirect(url_for('login', next=request.url))
        can_edit = False

    return render_template(
        'view_item.html',
        item=item,
        list=user_list,
        can_edit=can_edit,
        image_display_size=app.config.get('ITEM_IMAGE_DISPLAY_SIZE', 180)
    )


@app.route('/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    """Edit an item"""
    item = Item.query.get_or_404(item_id)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to edit this item.', 'error')
        return redirect(url_for('lists'))

    if request.method == 'POST':
        try:
            item.name = request.form.get('name', '').strip()
            item.description = request.form.get('description', '').strip()
            item.notes = request.form.get('notes', '').strip()
            item.tags = request.form.get('tags', '').strip()
            item_type_name = request.form.get('item_type', '').strip()
            item.location = request.form.get('location', '').strip()
            item.url = request.form.get('url', '').strip()
            item.barcode = request.form.get('barcode', '').strip()

            quantity = request.form.get('quantity', '1')
            try:
                item.quantity = int(quantity) if quantity else 1
            except ValueError:
                item.quantity = 1

            low_stock_threshold = request.form.get('low_stock_threshold', '0')
            try:
                item.low_stock_threshold = int(low_stock_threshold) if low_stock_threshold else 0
            except ValueError:
                item.low_stock_threshold = 0

            reminder_at_raw = request.form.get('reminder_at', '').strip()
            reminder_at = None
            if reminder_at_raw:
                try:
                    reminder_at = datetime.datetime.fromisoformat(reminder_at_raw)
                except ValueError:
                    reminder_at = None
            item.reminder_at = reminder_at

            # Get or create item type
            if item_type_name:
                item.item_type = ItemType.get_or_create(item_type_name, current_user.id)
            else:
                item.item_type = None

            if not item.name:
                flash('Item name is required.', 'error')
                return redirect(url_for('edit_item', item_id=item_id))

            item.set_tags_list(_parse_tags(item.tags))
            _save_attachments(item, request.files.getlist('attachments'))
            _save_item_images(item, request.files.getlist('images'))

            # Handle custom fields
            for field in user_list.get_custom_fields():
                custom_value = request.form.get(f'custom_{field.id}', '').strip()
                existing = item.get_custom_field_value(field.id)

                if field.field_type == 'text':
                    if custom_value:
                        if existing:
                            existing.value_text = custom_value
                        else:
                            custom_field = ItemCustomField(
                                item_id=item.id,
                                field_id=field.id,
                                value_text=custom_value
                            )
                            db.session.add(custom_field)
                    elif existing:
                        db.session.delete(existing)

                elif field.field_type == 'boolean':
                    is_checked = f'custom_{field.id}' in request.form
                    if is_checked:
                        if existing:
                            existing.value_bool = True
                        else:
                            custom_field = ItemCustomField(
                                item_id=item.id,
                                field_id=field.id,
                                value_bool=True
                            )
                            db.session.add(custom_field)
                    elif existing:
                        db.session.delete(existing)

                elif field.field_type == 'options':
                    if custom_value:
                        if existing:
                            existing.value_option = custom_value
                        else:
                            custom_field = ItemCustomField(
                                item_id=item.id,
                                field_id=field.id,
                                value_option=custom_value
                            )
                            db.session.add(custom_field)
                    elif existing:
                        db.session.delete(existing)

            db.session.commit()
            _log_action('update', 'item', item.id, {'name': item.name, 'list_id': user_list.id})
            flash('Item updated successfully!', 'success')
            return redirect(url_for('view_list', list_id=user_list.id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the item.', 'error')
            app.logger.error(f'Edit item error: {str(e)}')

    return render_template('edit_item.html', item=item, list=user_list)


@app.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    """Delete an item"""
    item = Item.query.get_or_404(item_id)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to delete this item.', 'error')
        return redirect(url_for('lists'))

    try:
        item_name = item.name
        list_id = item.list_id
        db.session.delete(item)
        db.session.commit()
        flash(f'Item "{item_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the item.', 'error')
        app.logger.error(f'Delete item error: {str(e)}')

    return redirect(url_for('view_list', list_id=list_id))


@app.route('/items/<int:item_id>/inline', methods=['POST'])
@login_required
def inline_update_item(item_id):
    """Inline update for item quantity/location."""
    item = Item.query.get_or_404(item_id)
    if item.list.user_id != current_user.id:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    if 'quantity' in data:
        try:
            item.quantity = int(data['quantity'])
        except (ValueError, TypeError):
            return jsonify({'error': 'invalid quantity'}), 400
    if 'location' in data:
        item.location = (data['location'] or '').strip()

    db.session.commit()
    _log_action('update', 'item', item.id, {'inline': True})
    return jsonify({'ok': True})


@app.route('/lists/<int:list_id>/items/bulk', methods=['POST'])
@login_required
def bulk_items(list_id):
    """Bulk actions for items in a list."""
    user_list = List.query.get_or_404(list_id)
    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to modify this list.', 'error')
        return redirect(url_for('lists'))

    action = request.form.get('action')
    item_ids = request.form.getlist('item_ids')
    item_ids = [int(i) for i in item_ids if i.isdigit()]
    if not item_ids:
        flash('No items selected.', 'error')
        return redirect(url_for('view_list', list_id=list_id))

    items = Item.query.filter(Item.id.in_(item_ids), Item.list_id == list_id).all()

    if action == 'delete':
        for item in items:
            db.session.delete(item)
        db.session.commit()
        _log_action('bulk_delete', 'item', list_id, {'count': len(items)})
        flash(f'Deleted {len(items)} items.', 'success')

    elif action == 'move':
        target_list_id = request.form.get('target_list_id')
        if not target_list_id or not target_list_id.isdigit():
            flash('Select a target list.', 'error')
            return redirect(url_for('view_list', list_id=list_id))
        target_list = List.query.get_or_404(int(target_list_id))
        if target_list.user_id != current_user.id:
            flash('Invalid target list.', 'error')
            return redirect(url_for('view_list', list_id=list_id))
        for item in items:
            item.list_id = target_list.id
        db.session.commit()
        _log_action('bulk_move', 'item', list_id, {'count': len(items), 'target': target_list.id})
        flash(f'Moved {len(items)} items.', 'success')

    elif action == 'tag':
        tag_input = request.form.get('bulk_tags', '')
        tags = _parse_tags(tag_input)
        for item in items:
            existing = item.get_tags_list()
            item.set_tags_list(sorted(set(existing + tags)))
        db.session.commit()
        _log_action('bulk_tag', 'item', list_id, {'count': len(items), 'tags': tags})
        flash(f'Updated tags for {len(items)} items.', 'success')

    else:
        flash('Invalid bulk action.', 'error')

    return redirect(url_for('view_list', list_id=list_id))


@app.route('/lists/<int:list_id>/export', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def export_items(list_id):
    """Export items in a list as CSV or JSON."""
    user_list = List.query.get_or_404(list_id)
    if user_list.user_id != current_user.id:
        flash('You do not have permission to export this list.', 'error')
        return redirect(url_for('lists'))

    format_type = request.args.get('format', 'json').lower()  # 'csv' or 'json'

    items = Item.query.filter_by(list_id=list_id).order_by(Item.created_at.desc()).all()

    if format_type == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['unique_id', 'name', 'description', 'notes', 'tags', 'item_type', 'location', 'quantity', 'barcode', 'low_stock_threshold', 'url', 'reminder_at'])
        for item in items:
            writer.writerow([
                item.unique_id,
                item.name,
                item.description or '',
                item.notes or '',
                ','.join(item.get_tags_list()),
                item.item_type.name if item.item_type else '',
                item.location or '',
                item.quantity,
                item.barcode or '',
                item.low_stock_threshold or 0,
                item.url or '',
                item.reminder_at.isoformat() if item.reminder_at else ''
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={user_list.name}_items.csv'}
        )
    else:  # JSON
        data = {
            'list': {
                'unique_id': user_list.unique_id,
                'name': user_list.name,
                'description': user_list.description,
                'tags': user_list.get_tags_list() if hasattr(user_list, 'get_tags_list') else []
            },
            'items': []
        }
        for item in items:
            data['items'].append({
                'unique_id': item.unique_id,
                'name': item.name,
                'description': item.description,
                'notes': item.notes,
                'tags': item.get_tags_list(),
                'item_type': item.item_type.name if item.item_type else None,
                'location': item.location,
                'quantity': item.quantity,
                'barcode': item.barcode,
                'low_stock_threshold': item.low_stock_threshold,
                'url': item.url,
                'reminder_at': item.reminder_at.isoformat() if item.reminder_at else None
            })

        import json
        return Response(
            json.dumps(data, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={user_list.name}_items.json'}
        )


@app.route('/lists/<int:list_id>/import', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")
def import_items(list_id):
    """Import items from CSV or JSON into a list with conflict resolution options."""
    user_list = List.query.get_or_404(list_id)
    if user_list.user_id != current_user.id:
        flash('You do not have permission to import into this list.', 'error')
        return redirect(url_for('lists'))

    if request.method == 'GET':
        # Show import form
        return render_template('import_items.html', list=user_list)

    # POST - handle the import
    file = request.files.get('import_file')
    conflict_action = request.form.get('conflict_action', 'ignore')  # 'ignore' or 'overwrite'

    if not file or not file.filename:
        flash('Please select a file to import.', 'error')
        return redirect(url_for('import_items', list_id=list_id))

    try:
        content = file.stream.read().decode('utf-8')
        filename = file.filename.lower()
        imported = 0
        skipped = 0
        updated = 0

        if filename.endswith('.json'):
            import json
            data = json.loads(content)
            items_data = data.get('items', [])
        elif filename.endswith('.csv'):
            reader = csv.DictReader(io.StringIO(content))
            items_data = list(reader)
        else:
            flash('File must be .csv or .json', 'error')
            return redirect(url_for('import_items', list_id=list_id))

        for row in items_data:
            name = (row.get('name') or '').strip()
            if not name:
                continue

            unique_id = row.get('unique_id', '').strip()

            # Check if item with this unique_id already exists
            existing_item = None
            if unique_id:
                existing_item = Item.query.filter_by(unique_id=unique_id, list_id=list_id).first()

            if existing_item:
                # Item already exists
                if conflict_action == 'overwrite':
                    # Update existing item
                    existing_item.name = name
                    existing_item.description = row.get('description') or ''
                    existing_item.notes = row.get('notes') or ''
                    existing_item.tags = row.get('tags') or ''
                    existing_item.location = row.get('location') or ''
                    existing_item.quantity = int(row.get('quantity') or 1)
                    existing_item.barcode = row.get('barcode') or ''
                    existing_item.low_stock_threshold = int(row.get('low_stock_threshold') or 0)
                    existing_item.url = row.get('url') or ''

                    if row.get('reminder_at'):
                        try:
                            existing_item.reminder_at = datetime.datetime.fromisoformat(row['reminder_at'])
                        except:
                            existing_item.reminder_at = None

                    if row.get('item_type'):
                        existing_item.item_type = ItemType.get_or_create(row.get('item_type'), current_user.id)

                    db.session.add(existing_item)
                    existing_item.set_tags_list(_parse_tags(row.get('tags') or ''))
                    updated += 1
                else:
                    # Skip existing item
                    skipped += 1
            else:
                # New item - create it
                item_type = None
                if row.get('item_type'):
                    item_type = ItemType.get_or_create(row.get('item_type'), current_user.id)

                import uuid as uuid_module
                new_unique_id = unique_id if unique_id else str(uuid_module.uuid4())

                new_item = Item(
                    unique_id=new_unique_id,
                    name=name,
                    description=row.get('description') or '',
                    notes=row.get('notes') or '',
                    tags=row.get('tags') or '',
                    item_type=item_type,
                    location=row.get('location') or '',
                    quantity=int(row.get('quantity') or 1),
                    barcode=row.get('barcode') or '',
                    low_stock_threshold=int(row.get('low_stock_threshold') or 0),
                    url=row.get('url') or '',
                    list_id=list_id
                )

                if row.get('reminder_at'):
                    try:
                        new_item.reminder_at = datetime.datetime.fromisoformat(row['reminder_at'])
                    except:
                        new_item.reminder_at = None

                db.session.add(new_item)
                db.session.flush()
                new_item.set_tags_list(_parse_tags(row.get('tags') or ''))
                imported += 1

        db.session.commit()
        _log_action('import', 'item', list_id, {'imported': imported, 'updated': updated, 'skipped': skipped})

        message = f'Import complete: {imported} new items, {updated} updated, {skipped} skipped.'
        flash(message, 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to import: {str(e)}', 'error')
        app.logger.error(f'Import error: {str(e)}')

    return redirect(url_for('view_list', list_id=list_id))


@app.route('/lists/export.csv')
@login_required
def export_lists_csv():
    """Export lists as CSV."""
    lists = List.query.filter_by(user_id=current_user.id, group_id=None).order_by(List.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'description', 'tags', 'created_at'])
    for lst in lists:
        writer.writerow([lst.name, lst.description or '', ','.join(lst.get_tags_list()), lst.created_at.isoformat()])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=lists.csv'})


@app.route('/attachments/<int:attachment_id>/download')
@login_required
def download_attachment(attachment_id):
    attachment = ItemAttachment.query.get_or_404(attachment_id)
    if attachment.item.list.user_id != current_user.id:
        flash('You do not have permission to access this attachment.', 'error')
        return redirect(url_for('lists'))
    directory = os.path.dirname(attachment.file_path)
    return send_from_directory(directory, os.path.basename(attachment.file_path), as_attachment=True, download_name=attachment.filename)


@app.route('/items/<int:item_id>/images/<int:image_id>/main', methods=['POST'])
@login_required
def set_item_image_main(item_id, image_id):
    item = Item.query.get_or_404(item_id)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to update images.', 'error')
        return redirect(url_for('view_item', item_id=item_id))

    target = ItemImage.query.filter_by(id=image_id, item_id=item_id).first()
    if not target:
        flash('Image not found.', 'error')
        return redirect(url_for('view_item', item_id=item_id))

    ItemImage.query.filter_by(item_id=item_id, is_main=True).update({'is_main': False})
    target.is_main = True
    db.session.commit()
    _log_action('set_main_image', 'item', item_id, {'image_id': image_id})
    flash('Main image updated.', 'success')
    return redirect(url_for('view_item', item_id=item_id, _anchor='item-images'))


@app.route('/items/<int:item_id>/images/delete', methods=['POST'])
@login_required
def delete_item_images(item_id):
    item = Item.query.get_or_404(item_id)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to delete images.', 'error')
        return redirect(url_for('view_item', item_id=item_id))

    image_ids = [int(i) for i in request.form.getlist('image_ids') if i.isdigit()]
    if not image_ids:
        flash('No images selected.', 'error')
        return redirect(url_for('view_item', item_id=item_id, _anchor='item-images'))

    images = ItemImage.query.filter(ItemImage.item_id == item_id, ItemImage.id.in_(image_ids)).all()
    for image in images:
        if image.storage_path and os.path.exists(image.storage_path):
            try:
                os.remove(image.storage_path)
            except OSError:
                pass
        db.session.delete(image)

    db.session.commit()

    remaining = ItemImage.query.filter_by(item_id=item_id).order_by(ItemImage.created_at.asc()).all()
    if remaining and not any(img.is_main for img in remaining):
        remaining[0].is_main = True
        db.session.commit()

    _log_action('delete_images', 'item', item_id, {'image_ids': image_ids})
    flash('Selected images deleted.', 'success')
    return redirect(url_for('view_item', item_id=item_id, _anchor='item-images'))


@app.route('/image-content/<path:filename>')
def image_content(filename):
    return send_from_directory(app.config['IMAGE_STORAGE_DIR'], filename)


@app.route('/item-types')
@login_required
def item_types():
    system_types = ItemType.query.filter_by(is_system=True, user_id=None).order_by(ItemType.name).all()
    user_types = ItemType.query.filter_by(is_system=False, user_id=current_user.id).order_by(ItemType.name).all()
    return render_template('item_types.html', system_types=system_types, user_types=user_types)


@app.route('/item-types/<int:type_id>/rename', methods=['POST'])
@login_required
def rename_item_type(type_id):
    item_type = ItemType.query.get_or_404(type_id)
    if item_type.is_system or item_type.user_id != current_user.id:
        flash('Cannot rename this type.', 'error')
        return redirect(url_for('item_types'))
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Name is required.', 'error')
        return redirect(url_for('item_types'))
    item_type.name = new_name
    db.session.commit()
    _log_action('rename', 'item_type', item_type.id, {'name': new_name})
    flash('Item type renamed.', 'success')
    return redirect(url_for('item_types'))


@app.route('/item-types/merge', methods=['POST'])
@login_required
def merge_item_type():
    source_id = request.form.get('source_id')
    target_id = request.form.get('target_id')
    if not (source_id and target_id and source_id.isdigit() and target_id.isdigit()):
        flash('Invalid merge selection.', 'error')
        return redirect(url_for('item_types'))
    source = ItemType.query.get_or_404(int(source_id))
    target = ItemType.query.get_or_404(int(target_id))
    if source.is_system or source.user_id != current_user.id:
        flash('Invalid source type.', 'error')
        return redirect(url_for('item_types'))
    if target.is_system is False and target.user_id != current_user.id:
        flash('Invalid target type.', 'error')
        return redirect(url_for('item_types'))

    Item.query.filter_by(item_type_id=source.id).update({'item_type_id': target.id})
    db.session.delete(source)
    db.session.commit()
    _log_action('merge', 'item_type', target.id, {'source': source.id})
    flash('Item type merged.', 'success')
    return redirect(url_for('item_types'))


@app.route('/item-types/<int:type_id>/delete', methods=['POST'])
@login_required
def delete_item_type(type_id):
    item_type = ItemType.query.get_or_404(type_id)
    if item_type.is_system or item_type.user_id != current_user.id:
        flash('Cannot delete this type.', 'error')
        return redirect(url_for('item_types'))
    Item.query.filter_by(item_type_id=item_type.id).update({'item_type_id': None})
    db.session.delete(item_type)
    db.session.commit()
    _log_action('delete', 'item_type', item_type.id, {})
    flash('Item type deleted.', 'success')
    return redirect(url_for('item_types'))


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


# ============= API Endpoints =============

@app.route('/api/item-types/autocomplete')
@login_required
def autocomplete_item_types():
    """API endpoint for item type autocomplete"""
    query = request.args.get('q', '').strip().lower()

    if not query or len(query) < 1:
        # Return all available types if no query
        available_types = ItemType.get_available_types(current_user.id)
        return jsonify([{'id': t.id, 'name': t.name} for t in available_types])

    # Search for matching types
    system_types = ItemType.query.filter(
        ItemType.is_system == True,
        ItemType.user_id == None,
        ItemType.name.ilike(f'%{query}%')
    ).all()

    user_types = ItemType.query.filter(
        ItemType.user_id == current_user.id,
        ItemType.name.ilike(f'%{query}%')
    ).all()

    results = [{'id': t.id, 'name': t.name} for t in system_types + user_types]
    return jsonify(results)


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
            return redirect(url_for('login'))

        if not user.verify_email_token(token):
            flash('Verification link has expired. Please register again.', 'error')
            return redirect(url_for('register'))

        user.confirm_email()
        db.session.commit()

        flash('Email verified successfully! You can now log in.', 'success')
        return redirect(url_for('login'))

    except Exception as e:
        app.logger.error(f'Email verification error: {str(e)}')
        flash('An error occurred during verification. Please try again.', 'error')
        return redirect(url_for('login'))


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
            return redirect(url_for('login'))

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
                return redirect(url_for('login'))
            else:
                flash('Password reset failed. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Password reset error: {str(e)}')
            flash('An error occurred during password reset. Please try again.', 'error')

    return render_template('reset_password.html', form=form, token=token)


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password for logged in user"""
    form = PasswordChangeForm()

    if form.validate_on_submit():
        try:
            # Verify current password
            if not current_user.check_password(form.current_password.data):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('change_password'))

            # Change password
            current_user.set_password(form.new_password.data)
            db.session.commit()

            # Send confirmation email
            from email_utils import send_password_changed_email
            send_password_changed_email(current_user)

            flash('Your password has been changed successfully.', 'success')
            return redirect(url_for('profile'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Password change error: {str(e)}')
            flash('An error occurred while changing password. Please try again.', 'error')

    return render_template('change_password.html', form=form)


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
                return redirect(url_for('login'))

            if user.email_verified:
                flash('Your email is already verified! You can log in now.', 'success')
                return redirect(url_for('login'))

            # Generate new verification token
            from email_utils import generate_token, send_verification_email

            verification_token = generate_token()
            user.set_email_verification_token(verification_token)
            db.session.commit()

            # Send verification email
            base_url = request.host_url.rstrip('/')
            send_verification_email(user, verification_token, base_url)

            flash('Verification email sent! Please check your inbox for the verification link.', 'success')
            return redirect(url_for('login'))

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
    """Export user's personal data in JSON format (GDPR right to data portability)"""
    try:
        import json
        from io import BytesIO

        # Collect all user data
        user_data = {
            'user': {
                'id': current_user.id,
                'username': current_user.username,
                'email': current_user.email,
                'created_at': current_user.created_at.isoformat() if current_user.created_at else None,
                'updated_at': current_user.updated_at.isoformat() if current_user.updated_at else None,
                'is_active': current_user.is_active,
                'preferences': current_user.preferences,
            },
            'lists': [],
            'items': [],
            'groups': [],
            'group_memberships': [],
            'list_shares': [],
            'notifications': [],
            'audit_logs': []
        }

        # Collect lists
        lists = List.query.filter_by(user_id=current_user.id).all()
        for lst in lists:
            user_data['lists'].append({
                'id': lst.id,
                'name': lst.name,
                'description': lst.description,
                'visibility': lst.visibility,
                'created_at': lst.created_at.isoformat() if lst.created_at else None,
                'updated_at': lst.updated_at.isoformat() if lst.updated_at else None,
                'items_count': len(lst.items)
            })

        # Collect items
        items = Item.query.filter(Item.list_id.in_(
            db.session.query(List.id).filter_by(user_id=current_user.id)
        )).all()
        for item in items:
            user_data['items'].append({
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'list_id': item.list_id,
                'quantity': item.quantity,
                'created_at': item.created_at.isoformat() if item.created_at else None,
                'updated_at': item.updated_at.isoformat() if item.updated_at else None,
            })

        # Collect groups owned
        groups = Group.query.filter_by(owner_id=current_user.id).all()
        for group in groups:
            user_data['groups'].append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'member_count': len(group.members)
            })

        # Collect group memberships
        memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
        for membership in memberships:
            user_data['group_memberships'].append({
                'group_id': membership.group_id,
                'group_name': membership.group.name,
                'role': membership.role,
                'joined_at': membership.joined_at.isoformat() if membership.joined_at else None,
            })

        # Collect list shares
        shares = ListShare.query.filter_by(user_id=current_user.id).all()
        for share in shares:
            user_data['list_shares'].append({
                'list_id': share.list_id,
                'list_name': share.list.name,
                'permission': share.permission,
                'shared_at': share.shared_at.isoformat() if share.shared_at else None,
            })

        # Collect notifications
        notifications = Notification.query.filter_by(user_id=current_user.id).all()
        for notif in notifications:
            user_data['notifications'].append({
                'id': notif.id,
                'type': notif.notification_type,
                'message': notif.message,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat() if notif.created_at else None,
            })

        # Collect audit logs
        logs = AuditLog.query.filter_by(user_id=current_user.id).all()
        for log in logs:
            user_data['audit_logs'].append({
                'id': log.id,
                'action': log.action,
                'entity': log.entity,
                'entity_id': log.entity_id,
                'created_at': log.created_at.isoformat() if log.created_at else None,
            })

        # Create JSON response
        json_data = json.dumps(user_data, indent=2)

        # Return as downloadable file
        from flask import send_file
        response = send_file(
            BytesIO(json_data.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'thinglist_data_export_{current_user.username}_{datetime.datetime.utcnow().strftime("%Y%m%d")}.json'
        )

        # Log the data export action
        _log_action('export', 'account_data', current_user.id, {'exported_at': datetime.datetime.utcnow().isoformat()})

        return response
    except Exception as e:
        app.logger.error(f'Data export error: {str(e)}')
        flash('An error occurred while exporting your data.', 'error')
        return redirect(url_for('profile'))


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

            # 5. Delete items in user's lists
            item_ids = db.session.query(Item.id).filter(
                Item.list_id.in_(db.session.query(List.id).filter_by(user_id=user_id))
            ).all()
            if item_ids:
                ItemImage.query.filter(ItemImage.item_id.in_(item_ids)).delete()
                ItemAttachment.query.filter(ItemAttachment.item_id.in_(item_ids)).delete()
                ItemCustomField.query.filter(ItemCustomField.item_id.in_(item_ids)).delete()
                Item.query.filter_by(user_id=user_id).delete()

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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
