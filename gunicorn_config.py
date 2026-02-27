"""
Gunicorn configuration for production deployment.

Usage:
    gunicorn -c gunicorn_config.py wsgi:app
"""
import os
import multiprocessing

# Server configuration
bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:5000')
backlog = 2048
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# Process naming
proc_name = 'thinglist'

# Server mechanics
daemon = False
umask = 0
user = None
group = None
tmp_upload_dir = None

# Logging
accesslog = '-'  # stdout
errorlog = '-'   # stderr
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Application
preload_app = False
paste = None

# SSL - Configure these if not using reverse proxy with SSL
keyfile = os.environ.get('GUNICORN_KEYFILE', None)
certfile = os.environ.get('GUNICORN_CERTFILE', None)
ssl_version = 'TLSv1_2'
cert_reqs = 0
ca_certs = None
suppress_ragged_eof = True
do_handshake_on_connect = True
ciphers = 'TLSv1'

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    print(f'[PRODUCTION] Gunicorn starting with {workers} workers')

def when_ready(server):
    """Called just after the server is started."""
    print('[PRODUCTION] Gunicorn is ready. Spawning workers')

def on_exit(server):
    """Called just before exiting Gunicorn."""
    print('[PRODUCTION] Gunicorn exiting gracefully')

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    print(f'[WORKER] Worker {worker.pid} spawned')

