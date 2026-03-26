from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp, Optional
from models import User, Group, InvitationToken, Location
from reserved_usernames import is_username_reserved


class RegistrationForm(FlaskForm):
    """Form for user registration"""
    username = StringField(
        'Username',
        validators=[
            DataRequired(message='Username is required'),
            Length(min=3, max=80, message='Username must be between 3 and 80 characters'),
            Regexp('^[A-Za-z0-9_]+$', message='Username must contain only letters, numbers, and underscores')
        ]
    )
    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email is required'),
            Email(message='Invalid email address')
        ]
    )
    password = PasswordField(
        'Password',
        validators=[
            DataRequired(message='Password is required'),
            Length(min=8, message='Password must be at least 8 characters long')
        ]
    )
    password_confirm = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(message='Please confirm your password'),
            EqualTo('password', message='Passwords must match')
        ]
    )
    invitation_token = HiddenField('Invitation Token', validators=[Optional()])
    submit = SubmitField('Create Account')

    def validate_username(self, field):
        """Check if username is reserved or already exists"""
        # Check if username is in the reserved list
        if is_username_reserved(field.data):
            raise ValidationError('This username is reserved and cannot be used. Please choose a different one.')

        # Check if username already exists
        user = User.query.filter_by(username=field.data).first()
        if user:
            raise ValidationError('Username already taken. Please choose a different one.')

    def validate_email(self, field):
        """Check if email already exists"""
        user = User.query.filter_by(email=field.data.lower()).first()
        if user:
            raise ValidationError('Email already registered. Please use a different email or login.')


class LoginForm(FlaskForm):
    """Form for user login - accepts username or email"""
    credential = StringField(
        'Username or Email',
        validators=[
            DataRequired(message='Username or email is required')
        ]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(message='Password is required')]
    )
    submit = SubmitField('Login')

    def validate_credential(self, field):
        """Check if user exists by username or email"""
        credential = field.data.lower().strip()

        # Try to find user by email first (faster for emails)
        user = User.query.filter_by(email=credential).first()

        # If not found by email, try username
        if not user:
            user = User.query.filter_by(username=credential).first()

        # Store the user object for use in validate_password
        self.user = user

        if not user:
            raise ValidationError('Username or email not found. Please register first.')

    def validate_password(self, field):
        """Check if password is correct"""
        # Use the user object stored in validate_credential
        if hasattr(self, 'user') and self.user:
            if not self.user.check_password(field.data):
                raise ValidationError('Invalid password. Please try again.')
        else:
            raise ValidationError('Cannot verify user. Please try again.')


class CreateGroupForm(FlaskForm):
    """Form for creating a new group"""
    name = StringField(
        'Group Name',
        validators=[
            DataRequired(message='Group name is required'),
            Length(min=3, max=120, message='Group name must be between 3 and 120 characters')
        ]
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000, message='Description must be 1000 characters or less')]
    )
    visibility = SelectField(
        'Group Visibility',
        choices=[
            ('private', 'Private - Only members can view lists and items'),
            ('public', 'Public - Anyone can view public lists and items')
        ],
        default='private',
        validators=[DataRequired()]
    )
    allow_members_create_lists = BooleanField(
        'Allow members to create lists',
        default=True
    )
    allow_members_edit_shared_lists = BooleanField(
        'Allow members to edit lists shared with group',
        default=True
    )
    submit = SubmitField('Create Group')


class EditGroupForm(FlaskForm):
    """Form for editing group settings"""
    name = StringField(
        'Group Name',
        validators=[
            DataRequired(message='Group name is required'),
            Length(min=3, max=120, message='Group name must be between 3 and 120 characters')
        ]
    )
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=1000, message='Description must be 1000 characters or less')]
    )
    visibility = SelectField(
        'Group Visibility',
        choices=[
            ('private', 'Private - Only members can view lists and items'),
            ('public', 'Public - Anyone can view public lists and items')
        ],
        validators=[DataRequired()]
    )
    allow_members_create_lists = BooleanField(
        'Allow members to create lists'
    )
    allow_members_edit_shared_lists = BooleanField(
        'Allow members to edit lists shared with group'
    )
    submit = SubmitField('Update Group')


class AddGroupMemberForm(FlaskForm):
    """Form for adding a member to a group"""
    username = StringField(
        'Username',
        validators=[
            DataRequired(message='Username is required'),
            Length(min=3, max=80, message='Username must be between 3 and 80 characters')
        ]
    )
    role = SelectField(
        'Role',
        choices=[
            ('member', 'Member'),
            ('admin', 'Administrator'),
            ('viewer', 'Viewer')
        ],
        default='member'
    )
    submit = SubmitField('Add Member')

    def validate_username(self, field):
        """Check if user exists"""
        user = User.query.filter_by(username=field.data.strip()).first()
        if not user:
            raise ValidationError(f'User "{field.data}" not found.')
        self.user = user


class EditGroupMemberForm(FlaskForm):
    """Form for editing group member role"""
    role = SelectField(
        'Role',
        choices=[
            ('member', 'Member'),
            ('admin', 'Administrator'),
            ('viewer', 'Viewer')
        ]
    )
    submit = SubmitField('Update Role')


class PasswordChangeForm(FlaskForm):
    """Form for changing user password"""
    current_password = PasswordField(
        'Current Password',
        validators=[
            DataRequired(message='Current password is required')
        ]
    )
    new_password = PasswordField(
        'New Password',
        validators=[
            DataRequired(message='New password is required'),
            Length(min=8, message='Password must be at least 8 characters long')
        ]
    )
    new_password_confirm = PasswordField(
        'Confirm New Password',
        validators=[
            DataRequired(message='Please confirm your password'),
            EqualTo('new_password', message='Passwords must match')
        ]
    )
    submit = SubmitField('Change Password')


class ForgotPasswordForm(FlaskForm):
    """Form for requesting password reset"""
    email = StringField(
        'Email Address',
        validators=[
            DataRequired(message='Email is required'),
            Email(message='Invalid email address')
        ]
    )
    submit = SubmitField('Request Password Reset')

    def validate_email(self, field):
        """Check if email exists"""
        user = User.query.filter_by(email=field.data.lower()).first()
        if not user:
            raise ValidationError('No account found with this email address.')


class ResetPasswordForm(FlaskForm):
    """Form for resetting password with token"""
    password = PasswordField(
        'New Password',
        validators=[
            DataRequired(message='Password is required'),
            Length(min=8, message='Password must be at least 8 characters long')
        ]
    )
    password_confirm = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(message='Please confirm your password'),
            EqualTo('password', message='Passwords must match')
        ]
    )
    submit = SubmitField('Reset Password')


class ItemTypeForm(FlaskForm):
    """Form for creating and editing item types"""
    name = StringField(
        'Item Type Name',
        validators=[
            DataRequired(message='Item type name is required'),
            Length(min=1, max=80, message='Item type name must be between 1 and 80 characters')
        ]
    )
    submit = SubmitField('Save Item Type')

    def validate_name(self, field):
        """Check if item type name already exists for this user"""
        from models import ItemType
        
        # Get the item type ID if editing (from session or context)
        item_type_id = None
        
        # Check if name already exists for this user (excluding the current item type if editing)
        existing = ItemType.query.filter(
            ItemType.name == field.data,
            ItemType.user_id == current_user.id,
            ItemType.is_system == False
        ).first()
        
        if existing:
            raise ValidationError('An item type with this name already exists.')


class LocationForm(FlaskForm):
    """Form for creating and editing locations"""
    name = StringField(
        'Location Name',
        validators=[
            DataRequired(message='Location name is required'),
            Length(min=1, max=150, message='Location name must be between 1 and 150 characters')
        ]
    )
    submit = SubmitField('Save Location')

    def validate_name(self, field):
        """Check if location name already exists for this user"""
        # Check if name already exists for this user (excluding the current location if editing)
        existing = Location.query.filter(
            Location.name == field.data,
            Location.user_id == current_user.id,
            Location.is_system == False
        ).first()
        
        if existing:
            raise ValidationError('A location with this name already exists.')
