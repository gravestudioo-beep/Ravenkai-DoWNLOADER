from __future__ import annotations
import os, time
from dataclasses import dataclass

@dataclass
class Metrics:
    started_at: float
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    bytes_sent: int = 0
    def uptime(self) -> int: return int(time.monotonic()-self.started_at)
    def snapshot(self): return {'uptime':self.uptime(),'completed':self.completed,'failed':self.failed,'cancelled':self.cancelled,'gb':self.bytes_sent/1024/1024/1024,'pid':os.getpid()}
