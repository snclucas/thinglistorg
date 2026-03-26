from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import func
import re

db = SQLAlchemy()


def generate_slug(name, id):
    """Generate a URL-friendly slug from name and id"""
    # Convert to lowercase and replace non-alphanumeric characters with hyphens
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    # Combine with id for uniqueness
    return f"{slug}-{id}".lower()


class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    preferences = db.Column(db.JSON, default=dict, nullable=False)  # JSON for storing user preferences

    # Email verification fields
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(255), unique=True, nullable=True, index=True)
    email_verification_token_expires = db.Column(db.DateTime, nullable=True)

    # Password reset fields
    password_reset_token = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_reset_token_expires = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def get_unread_notifications_count(self):
        """Get count of unread notifications"""
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()

    def get_unread_notifications(self):
        """Get all unread notifications"""
        return Notification.query.filter_by(user_id=self.id, is_read=False).order_by(Notification.created_at.desc()).all()

    def get_all_notifications(self, limit=20):
        """Get all notifications, newest first"""
        return Notification.query.filter_by(user_id=self.id).order_by(Notification.created_at.desc()).limit(limit).all()

    def get_items_per_page(self):
        """Get items per page preference (default 20, min 5, max 100)"""
        if not self.preferences:
            return 20
        per_page = self.preferences.get('items_per_page', 20)
        return min(max(int(per_page), 5), 100)

    def set_items_per_page(self, per_page):
        """Set items per page preference"""
        if not self.preferences:
            self.preferences = {}
        per_page = min(max(int(per_page), 5), 100)
        self.preferences['items_per_page'] = per_page
        return per_page

    # Email Verification Methods
    def set_email_verification_token(self, token, expires_hours=24):
        """Set email verification token"""
        from datetime import timedelta
        self.email_verification_token = token
        self.email_verification_token_expires = datetime.utcnow() + timedelta(hours=expires_hours)

    def verify_email_token(self, token):
        """Verify email verification token"""
        if self.email_verification_token != token:
            return False
        if self.email_verification_token_expires < datetime.utcnow():
            return False
        return True

    def confirm_email(self):
        """Mark email as verified"""
        self.email_verified = True
        self.email_verification_token = None
        self.email_verification_token_expires = None

    # Password Reset Methods
    def set_password_reset_token(self, token, expires_hours=2):
        """Set password reset token"""
        from datetime import timedelta
        self.password_reset_token = token
        self.password_reset_token_expires = datetime.utcnow() + timedelta(hours=expires_hours)

    def verify_password_reset_token(self, token):
        """Verify password reset token"""
        if self.password_reset_token != token:
            return False
        if self.password_reset_token_expires < datetime.utcnow():
            return False
        return True

    def reset_password(self, token, new_password):
        """Reset password if token is valid"""
        if not self.verify_password_reset_token(token):
            return False
        self.set_password(new_password)
        self.password_reset_token = None
        self.password_reset_token_expires = None
        return True

    # ...existing code...
    lists = db.relationship('List', backref='owner', lazy=True, cascade='all, delete-orphan', foreign_keys='List.user_id')
    # Relationship to custom item types
    item_types = db.relationship('ItemType', backref='user', lazy=True, cascade='all, delete-orphan')
    # Relationship to audit logs
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True, cascade='all, delete-orphan')
    # Relationship to groups will be added by Group.owner backref


# Association tables for normalized tags
list_tags = db.Table(
    'list_tags',
    db.Column('list_id', db.Integer, db.ForeignKey('lists.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
    db.Index('ix_list_tags_list_id', 'list_id'),
    db.Index('ix_list_tags_tag_id', 'tag_id')
)

item_tags = db.Table(
    'item_tags',
    db.Column('item_id', db.Integer, db.ForeignKey('items.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
    db.Index('ix_item_tags_item_id', 'item_id'),
    db.Index('ix_item_tags_tag_id', 'tag_id')
)


class Tag(db.Model):
    """Tag model for normalized tags"""
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('name', 'user_id', name='uq_tag_name_user'),
        db.Index('ix_tag_name', 'name'),
    )

    def __repr__(self):
        return f'<Tag {self.name}>'

    @staticmethod
    def normalize_tags(tags_list):
        """Normalize and dedupe tag list"""
        if not tags_list:
            return []
        return sorted({tag.strip().lower() for tag in tags_list if tag and tag.strip()})

    @staticmethod
    def get_or_create_many(tags_list, user_id):
        """Get or create tags for a user"""
        tags_list = Tag.normalize_tags(tags_list)
        if not tags_list:
            return []

        existing = Tag.query.filter(Tag.user_id == user_id, Tag.name.in_(tags_list)).all()
        existing_names = {t.name for t in existing}
        new_tags = []
        for tag_name in tags_list:
            if tag_name not in existing_names:
                new_tag = Tag(name=tag_name, user_id=user_id)
                db.session.add(new_tag)
                new_tags.append(new_tag)
        return existing + new_tags


class ListShare(db.Model):
    """ListShare model for managing user access to lists"""
    __tablename__ = 'list_shares'

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey('lists.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    permission = db.Column(db.String(20), nullable=False, default='view')  # 'view' or 'edit'
    shared_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Who shared it
    shared_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    list = db.relationship('List', backref='shares', lazy=True)
    user = db.relationship('User', foreign_keys=[user_id], backref='list_shares_as_user')
    shared_by = db.relationship('User', foreign_keys=[shared_by_id], backref='list_shares_shared_by')

    __table_args__ = (
        db.UniqueConstraint('list_id', 'user_id', name='uq_list_share_list_user'),
    )

    def __repr__(self):
        return f'<ListShare list={self.list_id} user={self.user_id} permission={self.permission}>'

    def can_view(self):
        """Check if user can view"""
        return self.permission in ('view', 'edit')

    def can_edit(self):
        """Check if user can edit"""
        return self.permission == 'edit'


class InvitationToken(db.Model):
    """Invitation token model for controlled user registration"""
    __tablename__ = 'invitation_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    max_uses = db.Column(db.Integer, default=1, nullable=False)
    times_used = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def __repr__(self):
        return f'<InvitationToken {self.token[:8]}...>'

    def is_valid(self):
        """Check if token is still valid"""
        if not self.is_active:
            return False
        if self.expires_at < datetime.utcnow():
            return False
        if self.max_uses > 0 and self.times_used >= self.max_uses:
            return False
        return True

    def use(self):
        """Mark token as used"""
        if self.is_valid():
            self.times_used += 1
            return True
        return False

    def remaining_uses(self):
        """Get remaining uses (-1 means unlimited)"""
        if self.max_uses <= 0:
            return -1
        return max(0, self.max_uses - self.times_used)


class Group(db.Model):
    """Group model for collaborative list management"""
    __tablename__ = 'groups'


    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(36), unique=True, nullable=True, index=True, 
                         default=lambda: str(__import__('uuid').uuid4()))  # Auto-generate UUID on insert
    slug = db.Column(db.String(200), unique=True, nullable=True, index=True)  # URL-friendly slug
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    visibility = db.Column(db.String(20), default='private', nullable=False)  # 'private', 'public'
    settings = db.Column(db.JSON, default=dict, nullable=False)  # Default permissions and settings
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_groups')
    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    lists = db.relationship('List', backref='group', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_groups_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<Group {self.name}>'

    def generate_slug(self):
        """Generate and set the slug from name and id"""
        if self.id:
            self.slug = generate_slug(self.name, self.id)
        return self.slug

    def to_dict(self):
        """Convert group to dictionary"""
        return {
            'id': self.id,
            'slug': self.slug,
            'name': self.name,
            'description': self.description,
            'owner_id': self.owner_id,
            'owner_username': self.owner.username,
            'member_count': len(self.members),
            'list_count': len(self.lists),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def get_default_settings(self):
        """Get default group settings"""
        return {
            'allow_members_create_lists': True,
            'allow_members_edit_shared_lists': True,
            'default_member_role': 'member',  # 'admin', 'member', 'viewer'
        }

    def get_settings(self):
        """Get group settings, applying defaults"""
        defaults = self.get_default_settings()
        if self.settings:
            defaults.update(self.settings)
        return defaults

    def set_settings(self, settings_dict):
        """Update group settings"""
        self.settings = settings_dict or {}

    def add_member(self, user_id, role='member', permissions=None):
        """Add a user to the group"""
        # Check if already a member
        existing = GroupMember.query.filter_by(group_id=self.id, user_id=user_id).first()
        if existing:
            return existing

        member = GroupMember(
            group_id=self.id,
            user_id=user_id,
            role=role,
            permissions=permissions
        )
        db.session.add(member)
        return member

    def remove_member(self, user_id):
        """Remove a user from the group"""
        member = GroupMember.query.filter_by(group_id=self.id, user_id=user_id).first()
        if member:
            db.session.delete(member)
            return True
        return False

    def get_members(self):
        """Get all members of the group"""
        return GroupMember.query.filter_by(group_id=self.id).order_by(GroupMember.joined_at.desc()).all()

    def get_member(self, user_id):
        """Get a specific member"""
        return GroupMember.query.filter_by(group_id=self.id, user_id=user_id).first()

    def is_owner(self, user_id):
        """Check if user is the group owner"""
        return self.owner_id == user_id

    def is_admin(self, user_id):
        """Check if user is an admin"""
        if self.is_owner(user_id):
            return True
        member = self.get_member(user_id)
        return member and member.role == 'admin'

    def user_has_role(self, user_id, role):
        """Check if user has a specific role"""
        if role == 'owner':
            return self.is_owner(user_id)
        member = self.get_member(user_id)
        if not member:
            return False
        return member.role == role

    def is_private(self):
        """Check if group is private (only members can see)"""
        return self.visibility == 'private'

    def is_public(self):
        """Check if group is public (everyone can view)"""
        return self.visibility == 'public'

    def user_can_access(self, user_id):
        """Check if a user can access this group (view lists and items)"""
        # Owner always has access
        if self.is_owner(user_id):
            return True
        
        # Check if user is a member
        if self.get_member(user_id):
            return True
        
        # If public, anyone can access
        if self.is_public():
            return True
        
        return False

    def user_can_manage(self, user_id):
        """Check if a user can manage this group (edit, add members)"""
        # Only owner and admins can manage
        return self.is_owner(user_id) or self.is_admin(user_id)


class GroupMember(db.Model):
    """GroupMember model for managing group membership"""
    __tablename__ = 'group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='member')  # 'admin', 'member', 'viewer'
    permissions = db.Column(db.JSON)  # User-specific permission overrides
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref='group_memberships')

    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='uq_group_member_group_user'),
    )

    def __repr__(self):
        return f'<GroupMember group={self.group_id} user={self.user_id} role={self.role}>'

    def has_permission(self, permission_key, group_settings=None):
        """Check if member has a specific permission"""
        # User-specific overrides take precedence
        if self.permissions and permission_key in self.permissions:
            return self.permissions[permission_key]

        # Fall back to role-based permissions
        if self.role == 'admin':
            return True  # Admins have all permissions
        if self.role == 'viewer':
            return permission_key in ('view_lists', 'view_items')
        if self.role == 'member':
            return permission_key in ('view_lists', 'view_items', 'create_lists', 'edit_lists', 'delete_lists')

        return False

    def can_view(self):
        """Check if member can view"""
        return self.role in ('admin', 'member', 'viewer')

    def can_edit(self):
        """Check if member can edit"""
        return self.role in ('admin', 'member')

    def can_manage(self):
        """Check if member can manage (admin actions)"""
        return self.role == 'admin'


class Notification(db.Model):
    """Notification model for user notifications"""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    notification_type = db.Column(db.String(50), nullable=False)  # 'share', 'permission_change', 'unshare'
    message = db.Column(db.String(500), nullable=False)
    list_id = db.Column(db.Integer, db.ForeignKey('lists.id'), nullable=True)
    shared_by_username = db.Column(db.String(80), nullable=True)  # Username of who shared/changed
    permission_level = db.Column(db.String(20), nullable=True)  # 'view' or 'edit'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = db.relationship('User', backref='notifications', lazy=True)
    list = db.relationship('List', backref='notifications', lazy=True)

    def __repr__(self):
        return f'<Notification user={self.user_id} type={self.notification_type}>'

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        return True

    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'type': self.notification_type,
            'message': self.message,
            'list_id': self.list_id,
            'list_name': self.list.name if self.list else 'Unknown List',
            'shared_by': self.shared_by_username,
            'permission': self.permission_level,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ItemAttachment(db.Model):
    """Attachment model for item files"""
    __tablename__ = 'item_attachments'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Attachment {self.filename}>'


class ItemImage(db.Model):
    """Image model for item photos"""
    __tablename__ = 'item_images'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    image_url = db.Column(db.String(500), nullable=False, unique=True)
    content_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)
    is_main = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_item_images_is_main', 'is_main'),
    )

    def __repr__(self):
        return f'<ItemImage {self.original_filename}>'


class AuditLog(db.Model):
    """Audit log model for tracking changes"""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    entity = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    meta = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity}:{self.entity_id}>'


class ItemType(db.Model):
    """ItemType model for predefined and custom item types"""
    __tablename__ = 'item_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, index=True)
    is_system = db.Column(db.Boolean, default=False)  # System types vs user-created
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)  # Null for system types
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ItemType {self.name}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'is_system': self.is_system
        }

    @staticmethod
    def get_available_types(user_id):
        """Get all available types for a user (system + user-created)"""
        system_types = ItemType.query.filter_by(is_system=True, user_id=None).all()
        user_types = ItemType.query.filter_by(user_id=user_id, is_system=False).all()
        return system_types + user_types

    @staticmethod
    def get_or_create(type_name, user_id):
        """Get existing type or create a new one for the user"""
        if not type_name or not type_name.strip():
            return None

        type_name = type_name.strip()
        type_name_lc = type_name.lower()

        # Check if system type exists (case-insensitive)
        system_type = ItemType.query.filter(
            ItemType.is_system == True,
            ItemType.user_id == None,
            func.lower(ItemType.name) == type_name_lc
        ).first()
        if system_type:
            return system_type

        # Check if user has created this type (case-insensitive)
        user_type = ItemType.query.filter(
            ItemType.user_id == user_id,
            ItemType.is_system == False,
            func.lower(ItemType.name) == type_name_lc
        ).first()
        if user_type:
            return user_type

        # Create new user type
        new_type = ItemType(name=type_name, user_id=user_id, is_system=False)
        db.session.add(new_type)
        db.session.flush()  # Flush to get the ID without committing
        return new_type


class Location(db.Model):
    """Location model for predefined and custom storage locations"""
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    is_system = db.Column(db.Boolean, default=False)  # System locations vs user-created
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)  # Null for system locations
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Location {self.name}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'is_system': self.is_system
        }

    @staticmethod
    def get_available_locations(user_id):
        """Get all available locations for a user (system + user-created)"""
        system_locations = Location.query.filter_by(is_system=True, user_id=None).order_by(Location.name).all()
        user_locations = Location.query.filter_by(user_id=user_id, is_system=False).order_by(Location.name).all()
        return system_locations + user_locations

    @staticmethod
    def get_or_create(location_name, user_id):
        """Get existing location or create a new one for the user"""
        if not location_name or not location_name.strip():
            return None

        location_name = location_name.strip()
        location_name_lc = location_name.lower()

        # Check if system location exists (case-insensitive)
        system_location = Location.query.filter(
            Location.is_system == True,
            Location.user_id == None,
            func.lower(Location.name) == location_name_lc
        ).first()
        if system_location:
            return system_location

        # Check if user has created this location (case-insensitive)
        user_location = Location.query.filter(
            Location.user_id == user_id,
            Location.is_system == False,
            func.lower(Location.name) == location_name_lc
        ).first()
        if user_location:
            return user_location

        # Create new user location
        new_location = Location(name=location_name, user_id=user_id, is_system=False)
        db.session.add(new_location)
        db.session.flush()  # Flush to get the ID without committing
        return new_location


class List(db.Model):
    """List model for inventory lists"""
    __tablename__ = 'lists'

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(__import__('uuid').uuid4()))  # UUID for export/import
    slug = db.Column(db.String(200), unique=True, nullable=True, index=True)  # URL-friendly slug
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    tags = db.Column(db.String(500))  # Comma-separated tags
    settings = db.Column(db.JSON)  # Field visibility and editability settings
    visibility = db.Column(db.String(20), default='private', nullable=False)  # 'private', 'public', 'hidden'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True, index=True)  # List belongs to a group

    # Relationship to items
    items = db.relationship('Item', backref='list', lazy=True, cascade='all, delete-orphan')
    # Relationship to tags
    tags_rel = db.relationship('Tag', secondary=list_tags, lazy='subquery', backref=db.backref('lists', lazy=True))
    # Relationship to custom fields
    custom_fields = db.relationship('ListCustomField', backref='list', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<List {self.name}>'

    def generate_slug(self):
        """Generate and set the slug from name and id"""
        if self.id:
            self.slug = generate_slug(self.name, self.id)
        return self.slug

    def to_dict(self):
        """Convert list to dictionary"""
        return {
            'id': self.id,
            'slug': self.slug,
            'name': self.name,
            'description': self.description,
            'tags': self.tags,
            'visibility': self.visibility,
            'item_count': len(self.items),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def is_private(self):
        """Check if list is private (only owner can see)"""
        return self.visibility == 'private'

    def is_public(self):
        """Check if list is public (visible in searches)"""
        return self.visibility == 'public'

    def is_hidden(self):
        """Check if list is hidden (link-only, not in searches)"""
        return self.visibility == 'hidden'

    def is_publicly_accessible(self):
        """Check if list is accessible to public (either public or hidden)"""
        # If list belongs to a private group, not publicly accessible
        if self.group_id:
            group = self.group
            if group and group.is_private():
                return False
        
        return self.visibility in ('public', 'hidden')

    def user_can_access(self, user_id):
        """Check if a user can access this list"""
        # Owner always has access
        if self.user_id == user_id:
            return True

        # If list belongs to a group, check group access first
        if self.group_id:
            group = self.group
            if group:
                # Check if user can access the group
                if not group.user_can_access(user_id):
                    # User can't access the group at all
                    return False
                
                # User can access group, check list-level permissions
                member = group.get_member(user_id)
                if member and member.can_view():
                    return True
                
                # For public groups: if list is public/hidden, user can access
                if group.is_public() and self.visibility in ('public', 'hidden'):
                    return True
                
                return False

        # Check if list is shared with user
        share = ListShare.query.filter_by(list_id=self.id, user_id=user_id).first()
        if share:
            return share.can_view()

        return False

    def user_can_edit(self, user_id):
        """Check if a user can edit this list"""
        # Owner always can edit
        if self.user_id == user_id:
            return True

        # If list belongs to a group, check group membership
        if self.group_id:
            group = self.group
            if group:
                member = group.get_member(user_id)
                if member:
                    # Admins and members can edit (unless overridden)
                    return member.has_permission('edit_lists') and member.can_edit()

        # Check if shared with edit permission
        share = ListShare.query.filter_by(list_id=self.id, user_id=user_id).first()
        if share:
            return share.can_edit()

        return False

    def get_shared_users(self):
        """Get all users this list is shared with"""
        shares = ListShare.query.filter_by(list_id=self.id).all()
        return [(share.user, share.permission) for share in shares]

    def share_with_user(self, user_id, permission='view', shared_by_id=None):
        """Share this list with another user"""
        # Check if already shared
        existing = ListShare.query.filter_by(list_id=self.id, user_id=user_id).first()
        if existing:
            existing.permission = permission
        else:
            share = ListShare(
                list_id=self.id,
                user_id=user_id,
                permission=permission,
                shared_by_id=shared_by_id or self.user_id
            )
            db.session.add(share)
        return True

    def revoke_user_access(self, user_id):
        """Remove access for a user"""
        share = ListShare.query.filter_by(list_id=self.id, user_id=user_id).first()
        if share:
            db.session.delete(share)
            return True
        return False

    def get_tags_list(self):
        """Return tags as a list"""
        if self.tags_rel:
            return [tag.name for tag in self.tags_rel]
        return [tag.strip() for tag in self.tags.split(',')] if self.tags else []

    def set_tags_list(self, tags_list):
        """Set tags from a list"""
        self.tags = ','.join(tags_list) if tags_list else ''
        if self.user_id:
            self.tags_rel = Tag.get_or_create_many(tags_list, self.user_id)

    def get_field_settings(self):
        """Get field visibility settings, return default if not set"""
        # If settings dict doesn't exist, return defaults
        if not self.settings:
            return self.get_default_field_settings()
        # If fields key doesn't exist in settings, return defaults
        if 'fields' not in self.settings:
            return self.get_default_field_settings()
        # Return the saved field settings
        return self.settings.get('fields', self.get_default_field_settings())

    @staticmethod
    def get_default_field_settings():
        """Get default field settings (all fields visible and editable)"""
        return {
            'name': {'visible': True, 'editable': True},
            'description': {'visible': True, 'editable': True},
            'notes': {'visible': False, 'editable': True},
            'quantity': {'visible': True, 'editable': True},
            'low_stock_threshold': {'visible': False, 'editable': True},
            'item_type': {'visible': True, 'editable': True},
            'location': {'visible': True, 'editable': True},
            'barcode': {'visible': False, 'editable': True},
            'url': {'visible': True, 'editable': True},
            'tags': {'visible': True, 'editable': True},
            'reminder_at': {'visible': False, 'editable': True},
            'attachments': {'visible': False, 'editable': True},
            'images': {'visible': True, 'editable': True},
        }

    def set_field_settings(self, field_settings):
        """Set field visibility settings"""
        if not self.settings:
            self.settings = {}
        self.settings['fields'] = field_settings

    def is_field_visible(self, field_name):
        """Check if a field is visible"""
        field_settings = self.get_field_settings()
        return field_settings.get(field_name, {}).get('visible', True)

    def is_field_editable(self, field_name):
        """Check if a field is editable"""
        field_settings = self.get_field_settings()
        return field_settings.get(field_name, {}).get('editable', True)

    def get_custom_fields(self):
        """Get custom fields ordered for display"""
        return sorted(self.custom_fields, key=lambda f: (f.sort_order or 0, f.name.lower()))


class ListCustomField(db.Model):
    """Custom field definition for a list"""
    __tablename__ = 'list_custom_fields'

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey('lists.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    field_type = db.Column(db.String(20), nullable=False)  # text, boolean, options
    options = db.Column(db.JSON)  # list of options for 'options' type
    is_visible = db.Column(db.Boolean, default=True, nullable=False)
    is_editable = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('list_id', 'name', name='uq_list_custom_field_name'),
    )

    def __repr__(self):
        return f'<ListCustomField {self.name}>'

    def get_options(self):
        """Return options list for options field"""
        return self.options or []


class ItemCustomField(db.Model):
    """Custom field value for an item"""
    __tablename__ = 'item_custom_fields'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False, index=True)
    field_id = db.Column(db.Integer, db.ForeignKey('list_custom_fields.id'), nullable=False, index=True)
    value_text = db.Column(db.Text)
    value_bool = db.Column(db.Boolean)
    value_option = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('item_id', 'field_id', name='uq_item_custom_field_item_field'),
    )

    def __repr__(self):
        return f'<ItemCustomField item={self.item_id} field={self.field_id}>'


class Item(db.Model):
    """Item model for inventory items"""
    __tablename__ = 'items'
    __table_args__ = (
        db.Index('ix_items_name', 'name'),
        db.Index('ix_items_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, index=True, default=lambda: str(__import__('uuid').uuid4()))  # UUID for export/import
    slug = db.Column(db.String(200), unique=True, nullable=True, index=True)  # URL-friendly slug
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    notes = db.Column(db.Text)
    tags = db.Column(db.String(500))  # Comma-separated tags
    quantity = db.Column(db.Integer, default=1)
    low_stock_threshold = db.Column(db.Integer, default=0)
    barcode = db.Column(db.String(128))
    url = db.Column(db.String(500))  # URL reference or product link
    reminder_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    list_id = db.Column(db.Integer, db.ForeignKey('lists.id'), nullable=False, index=True)
    item_type_id = db.Column(db.Integer, db.ForeignKey('item_types.id'), index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), index=True)

    # Relationship to ItemType
    item_type = db.relationship('ItemType', backref='items')
    # Relationship to Location
    location_obj = db.relationship('Location', backref='items')
    # Relationship to tags
    tags_rel = db.relationship('Tag', secondary=item_tags, lazy='subquery', backref=db.backref('items', lazy=True))
    # Relationship to attachments
    attachments = db.relationship('ItemAttachment', backref='item', lazy=True, cascade='all, delete-orphan')
    # Relationship to images
    images = db.relationship('ItemImage', backref='item', lazy=True, cascade='all, delete-orphan')
    # Relationship to custom field values
    custom_field_values = db.relationship('ItemCustomField', backref='item', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Item {self.name}>'

    def generate_slug(self):
        """Generate and set the slug from name and id"""
        if self.id:
            self.slug = generate_slug(self.name, self.id)
        return self.slug

    def to_dict(self):
        """Convert item to dictionary"""
        return {
            'id': self.id,
            'slug': self.slug,
            'name': self.name,
            'description': self.description,
            'notes': self.notes,
            'tags': self.tags,
            'item_type': self.item_type.name if self.item_type else None,
            'location': self.location,
            'quantity': self.quantity,
            'low_stock_threshold': self.low_stock_threshold,
            'barcode': self.barcode,
            'url': self.url,
            'reminder_at': self.reminder_at.isoformat() if self.reminder_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def get_tags_list(self):
        """Return tags as a list"""
        if self.tags_rel:
            return [tag.name for tag in self.tags_rel]
        return [tag.strip() for tag in self.tags.split(',')] if self.tags else []

    def set_tags_list(self, tags_list):
        """Set tags from a list"""
        self.tags = ','.join(tags_list) if tags_list else ''
        if self.list and self.list.user_id:
            self.tags_rel = Tag.get_or_create_many(tags_list, self.list.user_id)

    def get_custom_field_value(self, field_id):
        """Get custom field value for a specific field"""
        for value in self.custom_field_values:
            if value.field_id == field_id:
                return value
        return None

    def get_main_image(self):
        """Return the main image record if present."""
        for image in self.images:
            if image.is_main:
                return image
        return self.images[0] if self.images else None

    @property
    def is_low_stock(self):
        """Return True if item is below or equal to low stock threshold"""
        return self.low_stock_threshold and self.quantity <= self.low_stock_threshold

# Event listeners to automatically generate slugs
from sqlalchemy import event

@event.listens_for(Group, 'before_insert')
@event.listens_for(Group, 'before_update')
def generate_group_slug(mapper, connection, target):
    """Generate slug for Group before insert/update"""
    if target.id:
        target.generate_slug()

@event.listens_for(List, 'before_insert')
@event.listens_for(List, 'before_update')
def generate_list_slug(mapper, connection, target):
    """Generate slug for List before insert/update"""
    if target.id:
        target.generate_slug()

@event.listens_for(Item, 'before_insert')
@event.listens_for(Item, 'before_update')
def generate_item_slug(mapper, connection, target):
    """Generate slug for Item before insert/update"""
    if target.id:
        target.generate_slug()