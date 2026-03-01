"""
List and Item management routes for ThingList application.

This module handles all routes related to:
- List creation, viewing, editing, deletion
- List sharing and permissions
- Item creation, viewing, editing, deletion
- Item bulk operations, import/export
- Custom field management
- Item type and location management (autocomplete)
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_from_directory, send_file, Response, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text, and_, or_, func
from sqlalchemy.orm import attributes
from models import db, User, List, Item, ItemType, Tag, ItemAttachment, AuditLog, item_tags, ListCustomField, ItemCustomField, ListShare, Notification, ItemImage, Group, GroupMember, Location
from slug_utils import get_list_by_slug_or_id, get_item_by_slug_or_id
from forms import ItemTypeForm, LocationForm
import os
import csv
import io
import json
import time
import uuid as uuid_module
import datetime
import logging
from PIL import Image, UnidentifiedImageError

# Create blueprint
list_item_bp = Blueprint('list_item', __name__)

# Get logger
logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_tags(raw_tags):
    """Parse comma-separated tags string into list."""
    return [t.strip() for t in (raw_tags or '').split(',') if t.strip()]


def _log_action(action, entity, entity_id, meta=None):
    """Log an action to the audit log."""
    try:
        from models import AuditLog
        log = AuditLog(user_id=current_user.id, action=action, entity=entity, entity_id=entity_id, meta=meta)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _save_attachments(item, files):
    """Save file attachments to an item."""
    from models import ItemAttachment
    if not files:
        return
    for f in files:
        if not f or not f.filename:
            continue
        filename = secure_filename(f.filename)
        unique_name = f"{uuid_module.uuid4().hex}_{filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
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
    """Normalize image base URL to ensure trailing slash."""
    if not base_url:
        return '/'
    return base_url if base_url.endswith('/') else f"{base_url}/"


def _allowed_image_file(filename):
    """Check if file is an allowed image type."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('IMAGE_ALLOWED_EXTENSIONS', set())


def _convert_and_store_image(file_storage):
    """Convert and store image file, return ItemImage object."""
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed_image_file(file_storage.filename):
        return None

    output_format = (current_app.config.get('IMAGE_OUTPUT_FORMAT') or 'webp').lower()
    format_map = {'jpg': 'jpeg'}
    output_format = format_map.get(output_format, output_format)

    unique_name = f"{uuid_module.uuid4().hex}.{output_format}"
    storage_path = os.path.join(current_app.config['IMAGE_STORAGE_DIR'], unique_name)
    image_url = f"{_normalize_image_base_url(current_app.config.get('IMAGE_BASE_URL'))}{unique_name}"

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
    """Save image files to an item."""
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
            or_(
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


# ============================================================================
# LIST ROUTES
# ============================================================================

@list_item_bp.route('/lists')
@login_required
def lists():
    """View all user's lists (owned and shared)"""
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 5), 100)

    # Get owned lists - but exclude group lists (group_id is NULL means personal list)
    owned_lists_query = List.query.filter_by(user_id=current_user.id, group_id=None).order_by(List.created_at.desc())

    # Get shared lists (via ListShare)
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


@list_item_bp.route('/public-lists')
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


@list_item_bp.route('/lists/create', methods=['GET', 'POST'])
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
                return redirect(url_for('group.view_group', group_id=group_id))

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
                return redirect(url_for('list_item.create_list', group_id=group_id_form))

            # If group_id provided, verify user has access
            if group_id_form:
                group_check = Group.query.get(group_id_form)
                if not group_check or (not group_check.is_admin(current_user.id) and not group_check.is_owner(current_user.id)):
                    if group_check and not group_check.get_settings().get('allow_members_create_lists', True):
                        flash('You do not have permission to create lists in this group.', 'danger')
                        return redirect(url_for('group.view_group', group_id=group_id_form))

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

            # Generate slug now that list has an ID
            new_list.generate_slug()
            db.session.commit()

            _log_action('create', 'list', new_list.id, {'name': name, 'visibility': visibility, 'group_id': group_id_form})
            flash(f'List "{name}" created successfully!', 'success')
            return redirect(url_for('list_item.view_list', list_id=new_list.slug))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the list.', 'error')
            logger.error(f'Create list error: {str(e)}')

    return render_template('create_list.html', group=group)


@list_item_bp.route('/lists/<list_id>')
def view_list(list_id):
    """View a specific list and its items"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    # Check access permissions
    if current_user.is_authenticated:
        # Logged in user - check normal permissions
        if not user_list.user_can_access(current_user.id):
            flash('You do not have permission to view this list.', 'error')
            return redirect(url_for('list_item.lists'))
        can_edit = user_list.user_can_edit(current_user.id)
    else:
        # Not logged in - only allow public/hidden lists
        if not user_list.is_publicly_accessible():
            flash('You must log in to view this list.', 'info')
            return redirect(url_for('auth.login', next=request.url))
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

    base_query = _build_item_query(user_list.id, request.args)
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


@list_item_bp.route('/lists/<list_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_list(list_id):
    """Edit a list"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

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
                return redirect(url_for('list_item.edit_list', list_id=list_id))

            db.session.commit()
            _log_action('update', 'list', user_list.id, {'name': user_list.name, 'visibility': visibility})
            flash('List updated successfully!', 'success')
            return redirect(url_for('list_item.view_list', list_id=list_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the list.', 'error')
            logger.error(f'Edit list error: {str(e)}')

    return render_template('edit_list.html', list=user_list)


@list_item_bp.route('/lists/<list_id>/delete', methods=['POST'])
@login_required
def delete_list(list_id):
    """Delete a list"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to delete this list.', 'error')
        return redirect(url_for('list_item.lists'))

    try:
        list_name = user_list.name

        # Get all items in the list
        items = Item.query.filter_by(list_id=user_list.id).all()

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
        Item.query.filter_by(list_id=user_list.id).delete()

        # Delete all list shares
        ListShare.query.filter_by(list_id=user_list.id).delete()

        # Delete all custom fields in the list
        ListCustomField.query.filter_by(list_id=user_list.id).delete()

        # Now delete the list itself
        db.session.delete(user_list)
        db.session.commit()

        _log_action('delete', 'list', list_id, {'name': list_name})
        flash(f'List "{list_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the list.', 'error')
        logger.error(f'Delete list error: {str(e)}')

    return redirect(url_for('list_item.lists'))


@list_item_bp.route('/lists/<list_id>/settings', methods=['GET', 'POST'])
@login_required
def list_settings(list_id):
    """Configure list field visibility and editability settings"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

    if request.method == 'POST':
        try:
            # Log the incoming form data
            logger.info(f'Form data received: {dict(request.form)}')

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
                    logger.debug(f'Field {field}: visible={visible}, editable={editable}')

            # Log the settings being saved
            logger.info(f'Saving field settings for list {list_id}: {field_settings}')

            # Save settings
            user_list.set_field_settings(field_settings)
            logger.info(f'Settings object after set_field_settings: {user_list.settings}')

            # Mark the settings column as modified so SQLAlchemy detects the change
            attributes.flag_modified(user_list, 'settings')

            db.session.commit()
            logger.info(f'Settings saved successfully to database')

            _log_action('update_settings', 'list', user_list.id, {'settings': field_settings})
            flash('List settings updated successfully!', 'success')
            return redirect(url_for('list_item.view_list', list_id=list_id))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating settings.', 'error')
            logger.error(f'Update list settings error: {str(e)}')

    # Get current field settings
    field_settings = user_list.get_field_settings()
    
    return render_template('list_settings.html', list=user_list, field_settings=field_settings)


@list_item_bp.route('/lists/<list_id>/share', methods=['GET', 'POST'])
@login_required
def share_list(list_id):
    """Manage list sharing with other users"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    # Only owner can share
    if user_list.user_id != current_user.id:
        flash('You do not have permission to share this list.', 'error')
        return redirect(url_for('list_item.lists'))

    if request.method == 'POST':
        try:
            action = request.form.get('action')

            if action == 'add':
                username = request.form.get('username', '').strip()
                permission = request.form.get('permission', 'view')

                if not username:
                    flash('Please enter a username.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                # Find user by username
                share_user = User.query.filter_by(username=username).first()
                if not share_user:
                    flash(f'User "{username}" not found.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                # Can't share with self
                if share_user.id == current_user.id:
                    flash('You cannot share a list with yourself.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                # Check if already shared
                existing = ListShare.query.filter_by(list_id=user_list.id, user_id=share_user.id).first()
                if existing:
                    flash(f'This list is already shared with {username}.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                # Validate permission
                if permission not in ('view', 'edit'):
                    permission = 'view'

                # Create share
                share = ListShare(
                    list_id=user_list.id,
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
                    list_id=user_list.id,
                    shared_by_username=current_user.username,
                    permission_level=permission
                )
                db.session.add(notification)
                db.session.commit()

                _log_action('share', 'list', user_list.id, {
                    'shared_with': username,
                    'permission': permission
                })
                flash(f'List shared with {username} ({permission} permission)!', 'success')
                return redirect(url_for('list_item.share_list', list_id=list_id))

            elif action == 'remove':
                user_id = request.form.get('user_id')
                if not user_id or not user_id.isdigit():
                    flash('Invalid user.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                user_id = int(user_id)
                share = ListShare.query.filter_by(list_id=list_id, user_id=user_id).first()
                if not share:
                    flash('Share not found.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                removed_username = share.user.username
                removed_user_id = share.user_id

                db.session.delete(share)
                db.session.commit()

                # Create notification for removed user
                notification = Notification(
                    user_id=removed_user_id,
                    notification_type='unshare',
                    message=f'{current_user.username} revoked your access to the list "{user_list.name}"',
                    list_id=user_list.id,
                    shared_by_username=current_user.username
                )
                db.session.add(notification)
                db.session.commit()

                _log_action('unshare', 'list', user_list.id, {'removed_user': removed_username})
                flash(f'Revoked access for {removed_username}.', 'success')
                return redirect(url_for('list_item.share_list', list_id=list_id))

            elif action == 'update_permission':
                user_id = request.form.get('user_id')
                permission = request.form.get('permission', 'view')

                if not user_id or not user_id.isdigit():
                    flash('Invalid user.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

                if permission not in ('view', 'edit'):
                    permission = 'view'

                user_id = int(user_id)
                share = ListShare.query.filter_by(list_id=list_id, user_id=user_id).first()
                if not share:
                    flash('Share not found.', 'error')
                    return redirect(url_for('list_item.share_list', list_id=list_id))

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
                return redirect(url_for('list_item.share_list', list_id=list_id))

        except Exception as e:
            db.session.rollback()
            flash('An error occurred while managing shares.', 'error')
            logger.error(f'Share list error: {str(e)}')
            return redirect(url_for('list_item.share_list', list_id=list_id))

    # Get shared users
    shared_users = user_list.get_shared_users()

    return render_template('share_list.html', list=user_list, shared_users=shared_users)


# ============================================================================
# CUSTOM FIELD ROUTES
# ============================================================================

@list_item_bp.route('/lists/<list_id>/custom-fields/add', methods=['POST'])
@login_required
def add_custom_field(list_id):
    """Add a custom field to a list"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

    try:
        name = request.form.get('field_name', '').strip()
        field_type = request.form.get('field_type', 'text')

        if not name:
            flash('Field name is required.', 'error')
            return redirect(url_for('list_item.list_settings', list_id=list_id))

        # Check if field already exists
        existing = ListCustomField.query.filter_by(list_id=list_id, name=name).first()
        if existing:
            flash('A field with this name already exists.', 'error')
            return redirect(url_for('list_item.list_settings', list_id=list_id))

        # Parse options for option field type
        options = None
        if field_type == 'options':
            options_str = request.form.get('field_options', '').strip()
            if options_str:
                options = [opt.strip() for opt in options_str.split('\n') if opt.strip()]
            else:
                flash('Options are required for option fields.', 'error')
                return redirect(url_for('list_item.list_settings', list_id=list_id))

        # Get highest sort order
        max_sort = db.session.query(func.max(ListCustomField.sort_order)).filter_by(list_id=list_id).scalar() or 0

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
        logger.error(f'Add custom field error: {str(e)}')

    return redirect(url_for('list_item.list_settings', list_id=list_id))


@list_item_bp.route('/lists/<list_id>/custom-fields/<int:field_id>/delete', methods=['POST'])
@login_required
def delete_custom_field(list_id, field_id):
    """Delete a custom field from a list"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

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
        logger.error(f'Delete custom field error: {str(e)}')

    return redirect(url_for('list_item.list_settings', list_id=list_id))


@list_item_bp.route('/lists/<list_id>/custom-fields/<int:field_id>/toggle-visibility', methods=['POST'])
@login_required
def toggle_custom_field_visibility(list_id, field_id):
    """Toggle visibility of a custom field"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

    try:
        field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()
        field.is_visible = not field.is_visible
        db.session.commit()

        status = 'visible' if field.is_visible else 'hidden'
        flash(f'Field "{field.name}" is now {status}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred.', 'error')
        logger.error(f'Toggle visibility error: {str(e)}')

    return redirect(url_for('list_item.list_settings', list_id=list_id))


@list_item_bp.route('/lists/<list_id>/custom-fields/<int:field_id>/toggle-editable', methods=['POST'])
@login_required
def toggle_custom_field_editable(list_id, field_id):
    """Toggle editability of a custom field"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

    try:
        field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()
        field.is_editable = not field.is_editable
        db.session.commit()

        status = 'editable' if field.is_editable else 'read-only'
        flash(f'Field "{field.name}" is now {status}.', 'success')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred.', 'error')
        logger.error(f'Toggle editable error: {str(e)}')

    return redirect(url_for('list_item.list_settings', list_id=list_id))


@list_item_bp.route('/lists/<list_id>/custom-fields/<int:field_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_custom_field_name(list_id, field_id):
    """Edit a custom field name"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if user_list.user_id != current_user.id:
        flash('You do not have permission to edit this list.', 'error')
        return redirect(url_for('list_item.lists'))

    field = ListCustomField.query.filter_by(id=field_id, list_id=list_id).first_or_404()

    if request.method == 'POST':
        try:
            new_name = request.form.get('field_name', '').strip()

            if not new_name:
                flash('Field name cannot be empty.', 'error')
                return redirect(url_for('list_item.list_settings', list_id=list_id))

            # Check if the new name already exists (excluding the current field)
            existing = ListCustomField.query.filter_by(list_id=list_id, name=new_name).filter(
                ListCustomField.id != field_id
            ).first()

            if existing:
                flash(f'A field named "{new_name}" already exists in this list.', 'error')
                return redirect(url_for('list_item.list_settings', list_id=list_id))

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
            logger.error(f'Edit custom field name error: {str(e)}')

        return redirect(url_for('list_item.list_settings', list_id=list_id))

    # GET request - show edit form
    return render_template('edit_custom_field.html', list=user_list, field=field)


# ============================================================================
# ITEM ROUTES
# ============================================================================

@list_item_bp.route('/lists/<list_id>/items/create', methods=['GET', 'POST'])
@login_required
def create_item(list_id):
    """Create a new item in a list"""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to add items to this list.', 'error')
        return redirect(url_for('list_item.lists'))

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
                return redirect(url_for('list_item.create_item', list_id=list_id))

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

            # Get or create location
            location_obj = None
            if location:
                location_obj = Location.get_or_create(location, current_user.id)

            new_item = Item(
                name=name,
                description=description,
                notes=notes,
                tags=tags,
                item_type=item_type,
                location_obj=location_obj,
                quantity=quantity,
                url=url,
                barcode=barcode,
                low_stock_threshold=low_stock_threshold,
                reminder_at=reminder_at,
                list_id=user_list.id
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
            return redirect(url_for('list_item.view_list', list_id=list_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating the item.', 'error')
            logger.error(f'Create item error: {str(e)}')

    return render_template('create_item.html', list=user_list)


@list_item_bp.route('/items/<item_id>')
def view_item(item_id):
    """View item details"""
    item = get_item_by_slug_or_id(item_id)
    if not item:
        abort(404)
    user_list = item.list

    # Check access permissions
    if current_user.is_authenticated:
        # Logged in user - check normal permissions
        if not user_list.user_can_access(current_user.id):
            flash('You do not have permission to view this item.', 'error')
            return redirect(url_for('list_item.lists'))
        can_edit = user_list.user_can_edit(current_user.id)
    else:
        # Not logged in - only allow public/hidden lists
        if not user_list.is_publicly_accessible():
            flash('You must log in to view this item.', 'info')
            return redirect(url_for('auth.login', next=request.url))
        can_edit = False

    return render_template(
        'view_item.html',
        item=item,
        list=user_list,
        can_edit=can_edit,
        image_display_size=current_app.config.get('ITEM_IMAGE_DISPLAY_SIZE', 180)
    )


@list_item_bp.route('/items/<item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    """Edit an item"""
    item = get_item_by_slug_or_id(item_id)
    if not item:
        abort(404)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to edit this item.', 'error')
        return redirect(url_for('list_item.lists'))

    if request.method == 'POST':
        try:
            item.name = request.form.get('name', '').strip()
            item.description = request.form.get('description', '').strip()
            item.notes = request.form.get('notes', '').strip()
            item.tags = request.form.get('tags', '').strip()
            item_type_name = request.form.get('item_type', '').strip()
            location_name = request.form.get('location', '').strip()
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

            # Get or create location
            if location_name:
                item.location_obj = Location.get_or_create(location_name, current_user.id)
            else:
                item.location_obj = None

            if not item.name:
                flash('Item name is required.', 'error')
                return redirect(url_for('list_item.edit_item', item_id=item_id))

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
            return redirect(url_for('list_item.view_list', list_id=user_list.id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the item.', 'error')
            logger.error(f'Edit item error: {str(e)}')

    return render_template('edit_item.html', item=item, list=user_list)


@list_item_bp.route('/items/<item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    """Delete an item"""
    item = get_item_by_slug_or_id(item_id)
    if not item:
        abort(404)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to delete this item.', 'error')
        return redirect(url_for('list_item.lists'))

    try:
        item_name = item.name
        list_id = item.list_id
        db.session.delete(item)
        db.session.commit()
        flash(f'Item "{item_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the item.', 'error')
        logger.error(f'Delete item error: {str(e)}')

    return redirect(url_for('list_item.view_list', list_id=list_id))
@list_item_bp.route('/items/<item_id>/inline', methods=['POST'])
@login_required
def inline_update_item(item_id):
    """Inline update for item quantity/location."""
    item = get_item_by_slug_or_id(item_id)
    if not item:
        abort(404)
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


# ============================================================================
# ITEM BULK OPERATIONS
# ============================================================================

@list_item_bp.route('/lists/<list_id>/items/bulk', methods=['POST'])
@login_required
def bulk_items(list_id):
    """Bulk actions for items in a list."""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)
    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to modify this list.', 'error')
        return redirect(url_for('list_item.lists'))

    action = request.form.get('action')
    item_ids = request.form.getlist('item_ids')
    item_ids = [int(i) for i in item_ids if i.isdigit()]
    if not item_ids:
        flash('No items selected.', 'error')
        return redirect(url_for('list_item.view_list', list_id=list_id))

    items = Item.query.filter(Item.id.in_(item_ids), Item.list_id == user_list.id).all()

    if action == 'delete':
        for item in items:
            db.session.delete(item)
        db.session.commit()
        _log_action('bulk_delete', 'item', user_list.id, {'count': len(items)})
        flash(f'Deleted {len(items)} items.', 'success')

    elif action == 'move':
        target_list_id = request.form.get('target_list_id')
        if not target_list_id or not target_list_id.isdigit():
            flash('Select a target list.', 'error')
            return redirect(url_for('list_item.view_list', list_id=list_id))
        target_list = List.query.get_or_404(int(target_list_id))
        if target_list.user_id != current_user.id:
            flash('Invalid target list.', 'error')
            return redirect(url_for('list_item.view_list', list_id=list_id))
        for item in items:
            item.list_id = target_list.id
        db.session.commit()
        _log_action('bulk_move', 'item', user_list.id, {'count': len(items), 'target': target_list.id})
        flash(f'Moved {len(items)} items.', 'success')

    elif action == 'tag':
        tag_input = request.form.get('bulk_tags', '')
        tags = _parse_tags(tag_input)
        for item in items:
            existing = item.get_tags_list()
            item.set_tags_list(sorted(set(existing + tags)))
        db.session.commit()
        _log_action('bulk_tag', 'item', user_list.id, {'count': len(items), 'tags': tags})
        flash(f'Updated tags for {len(items)} items.', 'success')

    else:
        flash('Invalid bulk action.', 'error')

    return redirect(url_for('list_item.view_list', list_id=list_id))


# ============================================================================
# IMPORT/EXPORT ROUTES
# ============================================================================

@list_item_bp.route('/lists/<list_id>/export', methods=['GET'])
@login_required
def export_items(list_id):
    """Export items in a list as CSV or JSON."""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)
    if user_list.user_id != current_user.id:
        flash('You do not have permission to export this list.', 'error')
        return redirect(url_for('list_item.lists'))

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

        return Response(
            json.dumps(data, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename={user_list.name}_items.json'}
        )


@list_item_bp.route('/lists/<list_id>/import', methods=['GET', 'POST'])
@login_required
def import_items(list_id):
    """Import items from CSV or JSON into a list with conflict resolution options."""
    user_list = get_list_by_slug_or_id(list_id)
    if not user_list:
        abort(404)
    if user_list.user_id != current_user.id:
        flash('You do not have permission to import into this list.', 'error')
        return redirect(url_for('list_item.lists'))

    if request.method == 'GET':
        # Show import form
        return render_template('import_items.html', list=user_list)

    # POST - handle the import
    file = request.files.get('import_file')
    conflict_action = request.form.get('conflict_action', 'ignore')  # 'ignore' or 'overwrite'

    if not file or not file.filename:
        flash('Please select a file to import.', 'error')
        return redirect(url_for('list_item.import_items', list_id=list_id))

    try:
        content = file.stream.read().decode('utf-8')
        filename = file.filename.lower()
        imported = 0
        skipped = 0
        updated = 0

        if filename.endswith('.json'):
            data = json.loads(content)
            items_data = data.get('items', [])
        elif filename.endswith('.csv'):
            reader = csv.DictReader(io.StringIO(content))
            items_data = list(reader)
        else:
            flash('File must be .csv or .json', 'error')
            return redirect(url_for('list_item.import_items', list_id=list_id))

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
        logger.error(f'Import error: {str(e)}')

    return redirect(url_for('list_item.view_list', list_id=list_id))


@list_item_bp.route('/lists/export.csv')
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


# ============================================================================
# ATTACHMENT & IMAGE ROUTES
# ============================================================================

@list_item_bp.route('/attachments/<int:attachment_id>/download')
@login_required
def download_attachment(attachment_id):
    """Download an attachment from an item."""
    attachment = ItemAttachment.query.get_or_404(attachment_id)
    if attachment.item.list.user_id != current_user.id:
        flash('You do not have permission to access this attachment.', 'error')
        return redirect(url_for('list_item.lists'))
    directory = os.path.dirname(attachment.file_path)
    return send_from_directory(directory, os.path.basename(attachment.file_path), as_attachment=True, download_name=attachment.filename)


@list_item_bp.route('/items/<item_id>/images/<int:image_id>/main', methods=['POST'])
@login_required
def set_item_image_main(item_id, image_id):
    """Set an image as the main image for an item."""
    item = get_item_by_slug_or_id(item_id)
    if not item:
        abort(404)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to update images.', 'error')
        return redirect(url_for('list_item.view_item', item_id=item_id))

    target = ItemImage.query.filter_by(id=image_id, item_id=item_id).first()
    if not target:
        flash('Image not found.', 'error')
        return redirect(url_for('list_item.view_item', item_id=item_id))

    ItemImage.query.filter_by(item_id=item_id, is_main=True).update({'is_main': False})
    target.is_main = True
    db.session.commit()
    _log_action('set_main_image', 'item', item_id, {'image_id': image_id})
    flash('Main image updated.', 'success')
    return redirect(url_for('list_item.view_item', item_id=item_id, _anchor='item-images'))


@list_item_bp.route('/items/<item_id>/images/delete', methods=['POST'])
@login_required
def delete_item_images(item_id):
    """Delete images from an item."""
    item = get_item_by_slug_or_id(item_id)
    if not item:
        abort(404)
    user_list = item.list

    if not user_list.user_can_edit(current_user.id):
        flash('You do not have permission to delete images.', 'error')
        return redirect(url_for('list_item.view_item', item_id=item_id))

    image_ids = [int(i) for i in request.form.getlist('image_ids') if i.isdigit()]
    if not image_ids:
        flash('No images selected.', 'error')
        return redirect(url_for('list_item.view_item', item_id=item_id, _anchor='item-images'))

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
    return redirect(url_for('list_item.view_item', item_id=item_id, _anchor='item-images'))


@list_item_bp.route('/image-content/<path:filename>')
def image_content(filename):
    """Serve image content from storage."""
    return send_from_directory(current_app.config['IMAGE_STORAGE_DIR'], filename)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@list_item_bp.route('/api/item-types/autocomplete')
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


@list_item_bp.route('/api/locations/autocomplete')
@login_required
def autocomplete_locations():
    """API endpoint for location autocomplete"""
    query = request.args.get('q', '').strip().lower()

    if not query or len(query) < 1:
        # Return all available locations if no query
        available_locations = Location.get_available_locations(current_user.id)
        return jsonify([{'id': l.id, 'name': l.name} for l in available_locations])

    # Search for matching locations
    system_locations = Location.query.filter(
        Location.is_system == True,
        Location.user_id == None,
        Location.name.ilike(f'%{query}%')
    ).all()

    user_locations = Location.query.filter(
        Location.user_id == current_user.id,
        Location.name.ilike(f'%{query}%')
    ).all()

    results = [{'id': l.id, 'name': l.name} for l in system_locations + user_locations]
    return jsonify(results)
