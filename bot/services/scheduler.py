from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

@dataclass
class ScheduledJob:
    id: int
    user_id: int
    chat_id: int
    url: str
    run_at: float
    quality: str = '720'
    fmt: str = 'mp4'
    template: str = 'clean'
    title: str = 'Запланированная загрузка'
    cancelled: bool = False

class Scheduler:
    def __init__(self, poll_seconds: float = 1.5):
        self.poll_seconds = max(0.5, poll_seconds)
        self._task: asyncio.Task | None = None
        self._runner: Callable[[ScheduledJob], Awaitable[None]] | None = None
        self._loaded: dict[int, ScheduledJob] = {}

    async def start(self, runner: Callable[[ScheduledJob], Awaitable[None]], loader: Callable[[], Awaitable[list[dict]]]):
        self._runner = runner
        for row in await loader():
            self._loaded[int(row['id'])] = ScheduledJob(
                id=int(row['id']), user_id=int(row['user_id']), chat_id=int(row['chat_id']),
                url=row['url'], run_at=float(row['run_at']), quality=row['quality'], fmt=row['format'],
                template=row['template'], title=row['title'] or 'Запланированная загрузка'
            )
        self._task = asyncio.create_task(self._loop(), name='ravenkai-scheduler')

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self):
        while True:
            now = time.time()
            due = [j for j in self._loaded.values() if not j.cancelled and j.run_at <= now]
            for job in due:
                self._loaded.pop(job.id, None)
                try:
                    if self._runner:
                        await self._runner(job)
                except Exception:
                    # Runner records user-visible errors itself.
                    pass
            await asyncio.sleep(self.poll_seconds)

    def add(self, job: ScheduledJob):
        self._loaded[job.id] = job

    def cancel(self, job_id: int) -> bool:
        return self._loaded.pop(job_id, None) is not None

    def pending_for_user(self, user_id: int) -> list[ScheduledJob]:
        return sorted([j for j in self._loaded.values() if j.user_id == user_id and not j.cancelled], key=lambda x: x.run_at)
