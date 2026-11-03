from __future__ import annotations

try:
    from celery import Celery
except ImportError:  # local test environment without worker dependency
    Celery = None

from kusys.common.config import get_settings

settings = get_settings()
celery_app = None if Celery is None else Celery(
    "kusys",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["kusys.jobs.tasks"],
)
if celery_app is not None:
    celery_app.conf.update(
        task_track_started=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        timezone="UTC",
        beat_schedule={
            "recover-stale-jobs": {
                "task": "kusys.recover_stale_jobs",
                "schedule": 60.0,
            }
        },
    )
