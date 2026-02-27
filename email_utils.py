"""
Email utilities for sending emails via SMTP
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import secrets
from functools import wraps
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class EmailConfig:
    """Email configuration from environment variables"""

    def __init__(self):
        self.backend = os.getenv('EMAIL_BACKEND', 'console')
        self.from_email = os.getenv('EMAIL_FROM')
        self.admin_email = os.getenv('ADMIN_EMAIL')
        self.subject_prefix = os.getenv('EMAIL_SUBJECT_PREFIX', '[ThingList]')
        self.debug_to = os.getenv('EMAIL_DEBUG_TO', '')
        self.fail_silently = os.getenv('EMAIL_FAIL_SILENTLY', 'false').lower() == 'true'

        # SMTP Configuration
        self.smtp_host = os.getenv('EMAIL_SMTP_HOST')
        self.smtp_port = int(os.getenv('EMAIL_SMTP_PORT', 587))
        self.smtp_username = os.getenv('EMAIL_SMTP_USERNAME')
        self.smtp_password = os.getenv('EMAIL_SMTP_PASSWORD')
        self.smtp_use_tls = os.getenv('EMAIL_SMTP_USE_TLS', 'true').lower() == 'true'
        self.smtp_use_ssl = os.getenv('EMAIL_SMTP_USE_SSL', 'false').lower() == 'true'
        self.smtp_timeout = int(os.getenv('EMAIL_SMTP_TIMEOUT', 10))


config = EmailConfig()


def send_email(subject, to_email, html_content, text_content=None, from_email=None):
    """
    Send email via configured backend (smtp or console)

    Args:
        subject: Email subject line
        to_email: Recipient email address(es) - can be string or list
        html_content: HTML email body
        text_content: Plain text email body (optional)
        from_email: Sender email (uses config default if not provided)

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    if not config.from_email:
        logger.error('EMAIL_FROM not configured')
        return False

    from_email = from_email or config.from_email

    # Handle debug_to - send to specific email instead for testing
    if config.debug_to:
        to_email = config.debug_to

    # Ensure to_email is a list
    if isinstance(to_email, str):
        to_email = [to_email]

    if config.backend == 'smtp':
        return _send_smtp(subject, to_email, html_content, text_content, from_email)
    elif config.backend == 'console':
        return _send_console(subject, to_email, html_content, text_content)
    else:
        logger.error(f'Unknown email backend: {config.backend}')
        return False


def _send_smtp(subject, to_email, html_content, text_content, from_email):
    """Send email via SMTP"""
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"{config.subject_prefix} {subject}"
        msg['From'] = from_email
        msg['To'] = ', '.join(to_email) if isinstance(to_email, list) else to_email

        # Attach text and HTML versions
        if text_content:
            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        if html_content:
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        # Connect and send
        if config.smtp_use_ssl:
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=config.smtp_timeout)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=config.smtp_timeout)

        if config.smtp_use_tls:
            server.starttls()

        # Login if credentials provided
        if config.smtp_username and config.smtp_password:
            server.login(config.smtp_username, config.smtp_password)

        # Send email
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()

        logger.info(f'Email sent to {to_email}: {subject}')
        return True

    except Exception as e:
        logger.error(f'Error sending email: {str(e)}')
        if not config.fail_silently:
            raise
        return False


def _send_console(subject, to_email, html_content, text_content):
    """Send email to console (for development/testing)"""
    try:
        to_str = ', '.join(to_email) if isinstance(to_email, list) else to_email
        print(f"\n{'='*60}")
        print(f"EMAIL TO: {to_str}")
        print(f"SUBJECT: {config.subject_prefix} {subject}")
        print(f"{'='*60}")
        print(f"TEXT:\n{text_content or '(No text version)'}")
        print(f"\nHTML:\n{html_content}")
        print(f"{'='*60}\n")
        logger.info(f'Email logged to console: {subject}')
        return True
    except Exception as e:
        logger.error(f'Error logging email to console: {str(e)}')
        return False


def generate_token(length=32):
    """Generate a secure random token"""
    return secrets.token_urlsafe(length)


def send_verification_email(user, verification_token, base_url):
    """Send email verification link to user"""
    verification_link = f"{base_url}/verify-email/{verification_token}"

    subject = "Verify Your Email Address"

    html_content = f"""
    <html>
        <head></head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #0066cc;">Welcome to ThingList, {user.username}!</h2>
                
                <p>Thank you for registering. Please verify your email address to complete your account setup.</p>
                
                <p style="margin: 20px 0;">
                    <a href="{verification_link}" 
                       style="background-color: #0066cc; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Verify Email Address
                    </a>
                </p>
                
                <p style="color: #666; font-size: 0.9em;">
                    Or copy and paste this link in your browser:<br>
                    <code>{verification_link}</code>
                </p>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                
                <p style="color: #666; font-size: 0.85em;">
                    This link will expire in 24 hours.<br>
                    If you didn't register for this account, please ignore this email.
                </p>
            </div>
        </body>
    </html>
    """

    text_content = f"""
Welcome to ThingList, {user.username}!

Please verify your email address by visiting this link:
{verification_link}

This link will expire in 24 hours.

If you didn't register for this account, please ignore this email.
    """

    return send_email(subject, user.email, html_content, text_content)


def send_password_reset_email(user, reset_token, base_url):
    """Send password reset link to user"""
    reset_link = f"{base_url}/reset-password/{reset_token}"

    subject = "Reset Your Password"

    html_content = f"""
    <html>
        <head></head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #0066cc;">Password Reset Request</h2>
                
                <p>We received a request to reset your password. Click the button below to create a new password.</p>
                
                <p style="margin: 20px 0;">
                    <a href="{reset_link}" 
                       style="background-color: #0066cc; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Reset Password
                    </a>
                </p>
                
                <p style="color: #666; font-size: 0.9em;">
                    Or copy and paste this link in your browser:<br>
                    <code>{reset_link}</code>
                </p>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                
                <p style="color: #666; font-size: 0.85em;">
                    This link will expire in 2 hours.<br>
                    If you didn't request a password reset, please ignore this email and your password will remain unchanged.
                </p>
            </div>
        </body>
    </html>
    """

    text_content = f"""
Password Reset Request

We received a request to reset your password. Visit this link to create a new password:
{reset_link}

This link will expire in 2 hours.

If you didn't request this, please ignore this email.
    """

    return send_email(subject, user.email, html_content, text_content)


def send_password_changed_email(user):
    """Send confirmation that password has been changed"""
    subject = "Your Password Has Been Changed"

    html_content = f"""
    <html>
        <head></head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #0066cc;">Password Changed Successfully</h2>
                
                <p>Your password has been successfully changed. If you did not make this change, 
                   please contact us immediately.</p>
                
                <p style="color: #666; font-size: 0.9em;">
                    If you have any questions, please contact our support team.
                </p>
            </div>
        </body>
    </html>
    """

    text_content = """
Your password has been successfully changed.

If you did not make this change, please contact us immediately.
    """

    return send_email(subject, user.email, html_content, text_content)

