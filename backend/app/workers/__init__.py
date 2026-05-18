"""Background workers: the single-job indexing queue."""
from app.workers.queue import job_manager

__all__ = ["job_manager"]
