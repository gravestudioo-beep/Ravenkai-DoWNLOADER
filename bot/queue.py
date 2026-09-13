
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from collections import deque

@dataclass
class Job:
    user_id: int
    chat_id: int
    url: str
    quality: str='720'
    fmt: str='mp4'
    audio: bool=False
    request_message_id: int=0
    id: str=''
    cancelled: bool=False
    meta: dict = field(default_factory=dict)

class DownloadQueue:
    def __init__(self, max_concurrent=2):
        self.q: asyncio.Queue[Job] = asyncio.Queue()
        self.active: dict[int, Job] = {}
        self.by_id: dict[str, Job] = {}
        self.max_concurrent = max_concurrent
        self.workers=[]
        self.worker_handler=None

    async def start(self, handler):
        self.worker_handler=handler
        for _ in range(self.max_concurrent):
            task=asyncio.create_task(self.worker(), name='ravenkai-worker')
            self.workers.append(task)

    async def stop(self):
        for task in self.workers: task.cancel()
        if self.workers: await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

    async def put(self, job: Job):
        self.by_id[job.id]=job
        await self.q.put(job)

    def cancel_user(self, user_id: int) -> int:
        count=0
        for job in self.by_id.values():
            if job.user_id == user_id:
                job.cancelled=True; count += 1
        if user_id in self.active:
            self.active[user_id].cancelled=True
        return count

    def snapshot(self):
        return {'waiting': self.q.qsize(), 'active': len(self.active), 'jobs': len(self.by_id)}

    async def worker(self):
        while True:
            job = await self.q.get()
            self.active[job.user_id]=job
            try:
                if not job.cancelled:
                    await self.worker_handler(job)
            finally:
                self.active.pop(job.user_id, None)
                self.by_id.pop(job.id, None)
                self.q.task_done()
