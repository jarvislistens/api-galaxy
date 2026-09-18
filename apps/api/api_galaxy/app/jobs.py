"""A small async job runner with progress events.

Parsing and enrichment take long enough that the UI needs staged progress rather than a
spinner, and long enough that the user needs to be able to cancel. This is deliberately
in-process: a local single-user app does not need a broker, and adding one would make
"one command to start" impossible.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

MAX_RETAINED_JOBS = 100


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass
class Job:
    id: str
    kind: str
    project_id: str = ""
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    stage: str = "Queued"
    detail: str = ""
    result: Any = None
    error: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    events: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "project_id": self.project_id,
            "status": self.status.value,
            "progress": round(self.progress, 3),
            "stage": self.stage,
            "detail": self.detail,
            "error": self.error,
            "created_at": self.created_at,
            "result": self.result if self.status is JobStatus.SUCCEEDED else None,
        }


class JobCancelled(Exception):
    pass


class JobHandle:
    """What a job body uses to report progress and to notice cancellation."""

    def __init__(self, job: Job, manager: JobManager) -> None:
        self._job = job
        self._manager = manager

    @property
    def id(self) -> str:
        return self._job.id

    def check_cancelled(self) -> None:
        if self._job.status is JobStatus.CANCELLED:
            raise JobCancelled(self._job.id)

    async def progress(self, fraction: float, stage: str, detail: str = "") -> None:
        self.check_cancelled()
        self._job.progress = max(0.0, min(1.0, fraction))
        self._job.stage = stage
        self._job.detail = detail
        await self._manager.publish(self._job)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # -- lifecycle -----------------------------------------------------------------

    def create(self, kind: str, *, project_id: str = "") -> Job:
        job = Job(id=f"job:{uuid.uuid4().hex[:12]}", kind=kind, project_id=project_id)
        self._jobs[job.id] = job
        self._prune()
        return job

    def start(
        self,
        kind: str,
        body: Callable[[JobHandle], Awaitable[Any]],
        *,
        project_id: str = "",
    ) -> Job:
        job = self.create(kind, project_id=project_id)
        handle = JobHandle(job, self)

        async def runner() -> None:
            job.status = JobStatus.RUNNING
            job.stage = "Starting"
            await self.publish(job)
            try:
                job.result = await body(handle)
                if job.status is not JobStatus.CANCELLED:
                    job.status = JobStatus.SUCCEEDED
                    job.progress = 1.0
                    job.stage = "Done"
            except JobCancelled:
                job.status = JobStatus.CANCELLED
                job.stage = "Cancelled"
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                job.stage = "Cancelled"
                raise
            except Exception as exc:  # noqa: BLE001 - the job's failure is the job's result
                job.status = JobStatus.FAILED
                job.stage = "Failed"
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                await self.publish(job)
                self._tasks.pop(job.id, None)

        self._tasks[job.id] = asyncio.create_task(runner())
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        jobs = list(self._jobs.values())
        if project_id:
            jobs = [j for j in jobs if j.project_id == project_id]
        return [j.snapshot() for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)]

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status.terminal:
            return False
        job.status = JobStatus.CANCELLED
        job.stage = "Cancelling"
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        return True

    # -- events --------------------------------------------------------------------

    async def publish(self, job: Job) -> None:
        payload = job.snapshot()
        job.events.append(payload)
        for queue in list(self._subscribers.get(job.id, [])):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:  # pragma: no cover - slow consumer, drop the frame
                pass

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.setdefault(job_id, []).append(queue)
        job = self._jobs.get(job_id)
        if job is not None:
            queue.put_nowait(job.snapshot())
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(job_id)
        if not subscribers:
            return
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    def _prune(self) -> None:
        if len(self._jobs) <= MAX_RETAINED_JOBS:
            return
        finished = [j for j in self._jobs.values() if j.status.terminal]
        finished.sort(key=lambda j: j.created_at)
        for job in finished[: len(self._jobs) - MAX_RETAINED_JOBS]:
            self._jobs.pop(job.id, None)
            self._subscribers.pop(job.id, None)
