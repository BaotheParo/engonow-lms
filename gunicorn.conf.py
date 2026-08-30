"""
gunicorn.conf.py
================
Gunicorn multi-process configuration for ENGONOW AI Worker.
Includes child_exit hook to clean up dead worker metrics from PROMETHEUS_MULTIPROC_DIR.
"""

import os
from prometheus_client import multiprocess

bind = "0.0.0.0:8000"
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 65
timeout = 120
graceful_timeout = 30


def child_exit(server, worker):
    """
    Hook invoked when a child worker process terminates.
    Marks the process dead in the Prometheus multiprocess metric registry
    to prevent stale metric pollution and memory leaks.
    """
    try:
        multiprocess.mark_process_dead(worker.pid)
    except Exception as ex:
        # Avoid crashing master if multiprocess dir is not set
        pass
