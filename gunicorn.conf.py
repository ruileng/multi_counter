#!/usr/bin/env python3
"""
Gunicorn configuration for Multi Counter Web Application
Optimized for CentOS 8 production deployment
"""

import multiprocessing
import os

# Server socket
bind = f"{os.getenv('HOST', '127.0.0.1')}:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
worker_connections = 1000
timeout = 300  # 5 minutes for video processing
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "/var/log/multi-counter/access.log"
errorlog = "/var/log/multi-counter/error.log"
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "multi-counter"

# Daemon mode
daemon = False
pidfile = "/var/run/multi-counter/multi-counter.pid"
user = "multi-counter"
group = "multi-counter"

# Server mechanics
preload_app = True
sendfile = True
reuse_port = True

# SSL (if needed)
# keyfile = "/etc/ssl/private/multi-counter.key"
# certfile = "/etc/ssl/certs/multi-counter.crt"

# Environment
raw_env = [
    'DJANGO_SETTINGS_MODULE=myapp.settings',
    'FLASK_ENV=production',
]

def when_ready(server):
    server.log.info("Multi Counter server is ready. Listening on: %s", server.address)

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_exit(server, worker):
    server.log.info("Worker exited (pid: %s)", worker.pid) 