from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

class InfoCache:
    def __init__(self, root: str | Path, ttl: int = 900):
        self.path = Path(root); self.path.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
    def _file(self, url: str) -> Path:
        return self.path / (hashlib.sha256(url.strip().encode()).hexdigest() + '.json')
    def get(self, url: str):
        f=self._file(url)
        try:
            if time.time()-f.stat().st_mtime > self.ttl: return None
            return json.loads(f.read_text('utf-8'))
        except Exception: return None
    def set(self, url: str, data: dict):
        try: self._file(url).write_text(json.dumps(data, ensure_ascii=False), 'utf-8')
        except Exception: pass
    def clear(self):
        for f in self.path.glob('*.json'):
            try: f.unlink()
            except OSError: pass
