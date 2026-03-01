"""
Authentication routes for ThingList application
Handles user registration, login, and password management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db, User, InvitationToken
from forms import RegistrationForm, LoginForm, PasswordChangeForm

# Create Blueprint
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration - with optional invitation token"""
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    # Check invitation token from query string
    invitation_token = request.args.get('token') or request.form.get('invitation_token')
    valid_invitation = None
    
    if invitation_token:
        # Validate invitation token
        valid_invitation = InvitationToken.query.filter_by(token=invitation_token).first()
        if not valid_invitation or not valid_invitation.is_valid():
            flash('Invalid or expired invitation token.', 'error')
            return redirect(url_for('auth.login'))
    else:
        # Check if registrations are enabled
        if not current_app.config.get('REGISTRATIONS_ENABLED'):
            flash('Registration is currently disabled. Please use an invitation link or contact an administrator for access.', 'error')
            return redirect(url_for('auth.login'))

    form = RegistrationForm()
    
    # Set invitation token in hidden field if provided
    if invitation_token and request.method == 'GET':
        form.invitation_token.data = invitation_token
    
    # Validate reCAPTCHA if enabled (before form validation)
    if request.method == 'POST' and current_app.config.get('RECAPTCHA_ENABLED'):
        recaptcha_response = request.form.get('g-recaptcha-response')
        if not recaptcha_response:
            flash('Please complete the reCAPTCHA verification.', 'error')
            return render_template('register.html', form=form, invitation_token=invitation_token)
        
        # Verify with Google
        try:
            import requests
            verify_url = 'https://www.google.com/recaptcha/api/siteverify'
            verification_data = {
                'secret': current_app.config['RECAPTCHA_PRIVATE_KEY'],
                'response': recaptcha_response
            }
            recaptcha_result = requests.post(verify_url, data=verification_data, timeout=5)
            recaptcha_json = recaptcha_result.json()
            
            if not recaptcha_json.get('success'):
                flash('reCAPTCHA verification failed. Please try again.', 'error')
                return render_template('register.html', form=form, invitation_token=invitation_token)
        except Exception as e:
            current_app.logger.error(f'reCAPTCHA verification error: {str(e)}')
            flash('An error occurred during reCAPTCHA verification. Please try again.', 'error')
            return render_template('register.html', form=form, invitation_token=invitation_token)
    
    if form.validate_on_submit():
        try:
            # Re-validate invitation token on submit
            post_invitation = form.invitation_token.data
            if post_invitation:
                valid_invitation = InvitationToken.query.filter_by(token=post_invitation).first()
                if not valid_invitation or not valid_invitation.is_valid():
                    flash('Invalid or expired invitation token.', 'error')
                    return render_template('register.html', form=form, invitation_token=post_invitation)
            
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

            # Mark invitation token as used
            if valid_invitation:
                valid_invitation.use()
                db.session.commit()

            # Send verification email
            base_url = request.host_url.rstrip('/')
            send_verification_email(user, verification_token, base_url)

            flash('Registration successful! Please check your email to verify your account.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            current_app.logger.error(f'Registration error: {str(e)}')

    return render_template('register.html', form=form, invitation_token=invitation_token)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login with username or email"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()

    # Debug CSRF token on GET request
    if request.method == 'GET':
        current_app.logger.debug(f'LOGIN GET: Session ID present: {bool(request.cookies.get("session"))}')

    # Debug CSRF token on POST request
    if request.method == 'POST':
        current_app.logger.debug(f'LOGIN POST: Session ID present: {bool(request.cookies.get("session"))}')
        current_app.logger.debug(f'LOGIN POST: CSRF Token in form: {bool(request.form.get("csrf_token"))}')
        current_app.logger.debug(f'LOGIN POST: Form validation result: {form.validate_on_submit()}')
        if form.errors:
            current_app.logger.debug(f'LOGIN POST: Form errors: {form.errors}')

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
                return redirect(url_for('auth.login'))

            login_user(user, remember=request.form.get('remember') == 'on')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('lists'))
        else:
            flash('Invalid credentials. Please try again.', 'error')

    return render_template('login.html', form=form)


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password for logged in user"""
    form = PasswordChangeForm()

    if form.validate_on_submit():
        try:
            # Verify current password
            if not current_user.check_password(form.current_password.data):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('auth.change_password'))

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
            current_app.logger.error(f'Password change error: {str(e)}')
            flash('An error occurred while changing password. Please try again.', 'error')

    return render_template('change_password.html', form=form)
