"""Gunicorn config for the Satchemon API on CentOS.

Runs Uvicorn workers (ASGI) behind Gunicorn's process manager. Bound to
localhost only — nginx terminates the public connection and reverse-proxies.
"""

import multiprocessing

bind = "127.0.0.1:8080"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
