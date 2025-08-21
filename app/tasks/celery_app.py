from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure
from kombu import Exchange, Queue
import os
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = os.getenv("REDIS_PORT", "6379")
redis_password = os.getenv("REDIS_PASSWORD", "")
redis_db = os.getenv("REDIS_DB", "1")

if redis_password:
    broker_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
else:
    broker_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

app = Celery(
    "document_intelligence",
    broker=broker_url,
    backend=broker_url,
    include=[
        "app.tasks.document_tasks",
        "app.tasks.embedding_tasks",
        "app.tasks.indexing_tasks"
    ]
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    
    worker_prefetch_multiplier=2,
    worker_max_tasks_per_child=100,
    
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("documents", Exchange("documents"), routing_key="documents.*"),
        Queue("embeddings", Exchange("embeddings"), routing_key="embeddings.*"),
        Queue("indexing", Exchange("indexing"), routing_key="indexing.*"),
        Queue("priority", Exchange("priority"), routing_key="priority.*"),
    ),
    
    task_routes={
        "app.tasks.document_tasks.*": {"queue": "documents"},
        "app.tasks.embedding_tasks.*": {"queue": "embeddings"},
        "app.tasks.indexing_tasks.*": {"queue": "indexing"},
        "app.tasks.priority.*": {"queue": "priority"},
    },
    
    beat_schedule={
        "cleanup-old-cache": {
            "task": "app.tasks.maintenance.cleanup_cache",
            "schedule": timedelta(hours=6),
        },
        "optimize-indexes": {
            "task": "app.tasks.maintenance.optimize_indexes",
            "schedule": timedelta(days=1),
        },
        "generate-metrics-report": {
            "task": "app.tasks.maintenance.generate_metrics",
            "schedule": timedelta(hours=1),
        },
    },
    
    task_annotations={
        "*": {"rate_limit": "100/m"},
        "app.tasks.embedding_tasks.*": {"rate_limit": "50/m"},
    },
    
    result_expires=3600,
    result_persistent=True,
    result_compression="gzip",
    
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    logger.info(f"Task {task.name} [{task_id}] starting with args={args} kwargs={kwargs}")

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extra):
    logger.info(f"Task {task.name} [{task_id}] completed with state={state}")

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, **extra):
    logger.error(f"Task {sender.name} [{task_id}] failed: {exception}")

if __name__ == "__main__":
    app.start()