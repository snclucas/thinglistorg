"""
WSGI entry point for production deployment with Gunicorn.

Usage:
    gunicorn -w 4 -b 127.0.0.1:5000 wsgi:app

Or with nginx reverse proxy:
    gunicorn -w 4 -b 127.0.0.1:5000 --access-logfile - --error-logfile - wsgi:app
"""
import os
import logging
from app import app

# Configure logging
if not app.debug:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

if __name__ == '__main__':
    app.run(use_reloader=False)

