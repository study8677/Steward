"""Run Steward Celery worker from Python entrypoint."""

from __future__ import annotations

from steward.runtime.execution.celery_app import celery_app


def main() -> None:
    """Start celery worker."""
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=INFO",
            "--queues=steward.execution",
            "--pool=solo",
        ]
    )


if __name__ == "__main__":
    main()
