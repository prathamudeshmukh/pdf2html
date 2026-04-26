"""In-memory job store for async PDF conversion jobs.

Jobs are keyed by UUID and progress through:
  pending → processing → done | failed

Thread-safe: all mutations are protected by a single Lock so that
per-page progress increments from a ThreadPoolExecutor are atomic.
"""

import threading
import uuid
from typing import Optional


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "status": "pending",
                "pages_done": 0,
                "pages_total": 0,
                "result": None,
                "error": None,
            }
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def set_processing(self, job_id: str, pages_total: int) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "processing"
                self._jobs[job_id]["pages_total"] = pages_total

    def increment_page_done(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["pages_done"] += 1

    def set_done(self, job_id: str, result: dict) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "done"
                self._jobs[job_id]["result"] = result

    def set_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = error
