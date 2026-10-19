"""
Gunicorn configuration file with post-fork hook to fix Celery broker connection issue.

When Gunicorn forks worker processes, the parent's Celery broker connection pool
is shared (and broken) in child processes. This post_fork hook closes the connection
after each fork, forcing Celery to create fresh connections in each worker.
"""

import os


def post_fork(server, worker):
    """
    Called just after a worker has been forked.

    Note: eventlet.monkey_patch() is applied in wsgi.py before any imports.
    """
    server.log.info(f"Worker {worker.pid} spawned")


# Gunicorn server configuration
bind = "0.0.0.0:8060"
workers = 1  # Use 1 worker for simplicity with WebSockets
worker_class = "eventlet"  # Required for Socket.IO
worker_connections = 1000
# .env / compose set these. Defaults match the previous hardcoded values.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "120"))

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
