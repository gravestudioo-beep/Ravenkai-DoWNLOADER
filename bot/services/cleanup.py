from __future__ import annotations
import asyncio, time
from pathlib import Path

async def cleanup_loop(root: str | Path, max_age_hours: int = 24, interval: int = 1800):
    root=Path(root)
    while True:
        cutoff=time.time()-max_age_hours*3600
        for p in root.rglob('*'):
            if p.is_file() and p.stat().st_mtime < cutoff:
                try: p.unlink()
                except OSError: pass
        await asyncio.sleep(interval)
