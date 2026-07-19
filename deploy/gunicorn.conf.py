"""Gunicorn config for the MooreDnD portal backend on CentOS.

Runs Uvicorn workers (ASGI) behind Gunicorn's process manager. Bound to
localhost only — the reverse proxy (Apache/nginx) terminates the public
connection and path-routes /api to this process (PLAN §4).
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
