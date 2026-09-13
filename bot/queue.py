from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from itertools import count
from typing import Awaitable, Callable


@dataclass
class Job:
    user_id: int
    chat_id: int
    url: str
    quality: str = '720'
    fmt: str = 'mp4'
    audio: bool = False
    request_message_id: int = 0
    id: str = ''
    cancelled: bool = False
    priority: int = 10
    meta: dict = field(default_factory=dict)
    enqueued_at: float = 0.0


class DownloadQueue:
    """Priority queue with per-user limits and observable job state."""
    def __init__(self, max_concurrent: int = 2, per_user_limit: int = 3):
        self.q: asyncio.PriorityQueue[tuple[int, int, Job]] = asyncio.PriorityQueue()
        self._seq = count()
        self.active: dict[str, Job] = {}
        self.by_id: dict[str, Job] = {}
        self.max_concurrent = max(1, max_concurrent)
        self.per_user_limit = max(1, per_user_limit)
        self.workers: list[asyncio.Task] = []
        self.worker_handler: Callable[[Job], Awaitable[None]] | None = None
        self.paused = False

    async def start(self, handler):
        self.worker_handler = handler
        for _ in range(self.max_concurrent):
            self.workers.append(asyncio.create_task(self.worker(), name='ravenkai-worker'))

    async def stop(self):
        for task in self.workers:
            task.cancel()
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

    def user_pending_count(self, user_id: int) -> int:
        return sum(1 for job in self.by_id.values() if job.user_id == user_id and not job.cancelled)

    def has_duplicate(self, user_id: int, url: str) -> bool:
        canonical = url.strip().rstrip('/')
        return any(job.user_id == user_id and job.url.strip().rstrip('/') == canonical and not job.cancelled for job in self.by_id.values())

    async def put(self, job: Job):
        if self.paused:
            raise RuntimeError('Очередь временно приостановлена администратором.')
        if self.user_pending_count(job.user_id) >= self.per_user_limit:
            raise RuntimeError(f'Лимит очереди: не более {self.per_user_limit} задач одновременно.')
        self.by_id[job.id] = job
        job.enqueued_at = asyncio.get_running_loop().time()
        await self.q.put((job.priority, next(self._seq), job))

    def cancel_user(self, user_id: int) -> int:
        count_cancelled = 0
        for job in list(self.by_id.values()):
            if job.user_id == user_id and not job.cancelled:
                job.cancelled = True
                count_cancelled += 1
        return count_cancelled

    def cancel_job(self, job_id: str, user_id: int | None = None) -> bool:
        job = self.by_id.get(job_id)
        if not job or (user_id is not None and job.user_id != user_id):
            return False
        job.cancelled = True
        return True

    def position(self, job_id: str) -> int | None:
        job = self.by_id.get(job_id)
        if not job:
            return None
        if job_id in self.active:
            return 0
        pending = [j for j in self.by_id.values() if not j.cancelled and j.id != job_id]
        pending.sort(key=lambda j: (j.priority, j.enqueued_at))
        try:
            return pending.index(job) + 1
        except ValueError:
            return None

    def snapshot(self):
        waiting = sum(1 for j in self.by_id.values() if not j.cancelled and j.id not in self.active)
        return {'waiting': waiting, 'active': len(self.active), 'jobs': len(self.by_id), 'paused': self.paused}

    async def worker(self):
        while True:
            _, _, job = await self.q.get()
            try:
                if job.cancelled:
                    continue
                self.active[job.id] = job
                if self.worker_handler:
                    await self.worker_handler(job)
            finally:
                self.active.pop(job.id, None)
                self.by_id.pop(job.id, None)
                self.q.task_done()
