
from __future__ import annotations

from pathlib import Path
from typing import Any
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / 'data' / 'ravenkai.db'
LEGACY_DB_PATH = BASE_DIR / 'database' / 'ravenkai.db'

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    username TEXT DEFAULT '',
    registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    videos INTEGER DEFAULT 0,
    audio INTEGER DEFAULT 0,
    downloaded_mb REAL DEFAULT 0,
    banned INTEGER DEFAULT 0,
    premium INTEGER DEFAULT 0,
    premium_until TEXT,
    quality TEXT DEFAULT '720',
    format TEXT DEFAULT 'mp4',
    auto_delete INTEGER DEFAULT 1,
    notifications INTEGER DEFAULT 1,
    trial_used INTEGER DEFAULT 0,
    trial_started_at TEXT,
    trial_until TEXT
);
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    platform TEXT DEFAULT '',
    title TEXT DEFAULT '',
    duration INTEGER DEFAULT 0,
    quality TEXT DEFAULT 'best',
    format TEXT DEFAULT 'mp4',
    size_mb REAL DEFAULT 0,
    status TEXT DEFAULT 'queued',
    error TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'XTR',
    charge_id TEXT NOT NULL UNIQUE,
    product TEXT NOT NULL DEFAULT 'premium',
    days INTEGER NOT NULL DEFAULT 30,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    title TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id,url)
);
CREATE INDEX IF NOT EXISTS idx_downloads_user_created ON downloads(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(user_id);
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    run_at REAL NOT NULL,
    quality TEXT DEFAULT '720',
    format TEXT DEFAULT 'mp4',
    template TEXT DEFAULT 'clean',
    title TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scheduled_user_run ON scheduled_jobs(user_id, run_at);
"""

NEXT_SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,name));
CREATE TABLE IF NOT EXISTS collection_items (collection_id INTEGER NOT NULL, bookmark_id INTEGER NOT NULL, PRIMARY KEY(collection_id,bookmark_id));
CREATE TABLE IF NOT EXISTS user_profiles (user_id INTEGER PRIMARY KEY, filename_template TEXT DEFAULT '{title}_{id}', download_profile TEXT DEFAULT 'balanced');
CREATE TABLE IF NOT EXISTS recurring_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,url TEXT NOT NULL,cadence TEXT NOT NULL,hour INTEGER DEFAULT 12,minute INTEGER DEFAULT 0,weekday INTEGER DEFAULT 0,quality TEXT DEFAULT '720',format TEXT DEFAULT 'mp4',template TEXT DEFAULT 'clean',enabled INTEGER DEFAULT 1,last_run TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS retry_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,url TEXT NOT NULL,attempts INTEGER DEFAULT 0,next_at REAL NOT NULL,last_error TEXT DEFAULT '',status TEXT DEFAULT 'waiting',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS backup_runs (id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,size_mb REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_recurring_user_enabled ON recurring_jobs(user_id,enabled);
"""

class _AsyncCursor:
    """Tiny async facade over sqlite3.Cursor so existing bot code stays async."""
    def __init__(self, cursor):
        self._cursor = cursor

    async def fetchone(self):
        return self._cursor.fetchone()

    async def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount


class _AsyncDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn = None

    async def __aenter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() and LEGACY_DB_PATH.exists():
            try:
                import shutil
                shutil.copy2(LEGACY_DB_PATH, self.path)
            except OSError:
                pass
        self.conn = sqlite3.connect(
            self.path,
            timeout=30,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.conn is None:
            return False
        try:
            if exc_type:
                self.conn.rollback()
            self.conn.close()
        finally:
            self.conn = None
        return False

    async def execute(self, sql, params=()):
        return _AsyncCursor(self.conn.execute(sql, params))

    async def executescript(self, sql):
        self.conn.executescript(sql)

    async def commit(self):
        self.conn.commit()

    async def rollback(self):
        self.conn.rollback()


def connect():
    """Open the single local SQLite file: data/ravenkai.db."""
    return _AsyncDB(DB_PATH)


async def init_db():
    async with connect() as db:
        await db.executescript(SCHEMA)
        # Backward-compatible columns for older ravenkai.db files.
        cur = await db.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in await cur.fetchall()}
        for col, ddl in {
            'trial_used': 'ALTER TABLE users ADD COLUMN trial_used INTEGER DEFAULT 0',
            'trial_started_at': 'ALTER TABLE users ADD COLUMN trial_started_at TEXT',
            'trial_until': 'ALTER TABLE users ADD COLUMN trial_until TEXT',
        }.items():
            if col not in cols:
                await db.execute(ddl)
        await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('maintenance','0')")
        await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('max_queue','2')")
        await db.commit()

async def ensure_user(user_id: int, name: str, username: str = ''):
    async with connect() as db:
        cur = await db.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        exists = await cur.fetchone()
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id,name,username) VALUES(?,?,?)",
            (user_id, name, username or ''),
        )
        await db.execute(
            "UPDATE users SET name=?, username=?, last_seen=CURRENT_TIMESTAMP WHERE user_id=?",
            (name, username or '', user_id),
        )
        if (not exists) or (exists and int(exists[0] or 0) == 0):
            cur2 = await db.execute("SELECT trial_until, premium FROM users WHERE user_id=?", (user_id,))
            u2 = await cur2.fetchone()
            if u2 and not u2[0] and not u2[1]:
                await db.execute("UPDATE users SET trial_used=1, trial_started_at=COALESCE(trial_started_at,CURRENT_TIMESTAMP), trial_until=COALESCE(trial_until,datetime('now','+3 days')) WHERE user_id=?", (user_id,))
        await db.commit()

async def get_user(user_id: int):
    async with connect() as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()

async def trial_active(user_id: int) -> bool:
    async with connect() as db:
        row = await (await db.execute("SELECT trial_until FROM users WHERE user_id=?", (user_id,))).fetchone()
        if not row or not row[0]:
            return False
        return str(row[0]) > __import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

async def trial_days_left(user_id: int) -> int:
    async with connect() as db:
        row = await (await db.execute("SELECT trial_until FROM users WHERE user_id=?", (user_id,))).fetchone()
        if not row or not row[0]: return 0
        cur = __import__('datetime').datetime.fromisoformat(str(row[0]))
        delta = cur - __import__('datetime').datetime.utcnow()
        return max(0, delta.days + (1 if delta.seconds else 0))

async def record_payment(user_id: int, payload: str, amount: int, currency: str, charge_id: str, product: str, days: int):
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO payments(user_id,payload,amount,currency,charge_id,product,days) VALUES(?,?,?,?,?,?,?)", (user_id,payload,amount,currency,charge_id,product,days))
        await db.commit()

async def payment_history(limit: int = 100):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM payments ORDER BY id DESC LIMIT ?", (limit,))).fetchall()

async def set_user_field(user_id: int, field: str, value: Any):
    allowed = {'quality','format','auto_delete','notifications','premium','premium_until','banned','trial_used','trial_started_at','trial_until'}
    if field not in allowed:
        raise ValueError('unsupported field')
    async with connect() as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
        await db.commit()

async def record_download(user_id: int, url: str, platform: str, title: str, duration: int,
                          quality: str, fmt: str, size_mb: float, status: str='done', error: str=''):
    async with connect() as db:
        await db.execute(
            "INSERT INTO downloads(user_id,url,platform,title,duration,quality,format,size_mb,status,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id,url,platform,title or '',int(duration or 0),quality,fmt,float(size_mb or 0),status,error or '')
        )
        if status == 'done':
            if fmt in {'mp3','m4a','audio'}:
                await db.execute("UPDATE users SET audio=audio+1, downloaded_mb=downloaded_mb+? WHERE user_id=?", (size_mb,user_id))
            else:
                await db.execute("UPDATE users SET videos=videos+1, downloaded_mb=downloaded_mb+? WHERE user_id=?", (size_mb,user_id))
        await db.commit()

async def history(user_id: int, limit: int=10, offset: int=0):
    async with connect() as db:
        cur = await db.execute(
            "SELECT * FROM downloads WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        )
        return await cur.fetchall()

async def get_download(user_id: int, item_id: int):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM downloads WHERE user_id=? AND id=?", (user_id, item_id))).fetchone()

async def download_stats(user_id: int):
    async with connect() as db:
        row = await (await db.execute("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),0) AS done,
                   COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END),0) AS failed,
                   COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) AS cancelled,
                   COALESCE(SUM(CASE WHEN status='done' THEN size_mb ELSE 0 END),0) AS mb,
                   COALESCE(SUM(CASE WHEN status='done' AND format IN ('mp3','m4a','audio') THEN 1 ELSE 0 END),0) AS audio,
                   COALESCE(SUM(CASE WHEN status='done' AND format NOT IN ('mp3','m4a','audio') THEN 1 ELSE 0 END),0) AS video
            FROM downloads WHERE user_id=?
        """, (user_id,))).fetchone()
        return dict(row) if row else {}

async def search_history(user_id: int, query: str, limit: int = 10):
    async with connect() as db:
        like = f"%{query.strip()}%"
        return await (await db.execute("""
            SELECT * FROM downloads
            WHERE user_id=? AND (title LIKE ? OR url LIKE ? OR platform LIKE ?)
            ORDER BY id DESC LIMIT ?
        """, (user_id, like, like, like, limit))).fetchall()

async def delete_history_item(user_id: int, item_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM downloads WHERE user_id=? AND id=?", (user_id,item_id))
        await db.commit()

async def clear_history(user_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM downloads WHERE user_id=?", (user_id,))
        await db.commit()

async def count_history(user_id: int):
    async with connect() as db:
        row = await (await db.execute("SELECT COUNT(*) FROM downloads WHERE user_id=?", (user_id,))).fetchone()
        return int(row[0])

async def log_action(user_id: int | None, action: str, details: str=''):
    async with connect() as db:
        await db.execute("INSERT INTO logs(user_id,action,details) VALUES(?,?,?)", (user_id,action,details[:1500]))
        await db.commit()

async def get_setting(key: str, default: str=''):
    async with connect() as db:
        row = await (await db.execute("SELECT value FROM settings WHERE key=?", (key,))).fetchone()
        return row[0] if row else default

async def set_setting(key: str, value: str):
    async with connect() as db:
        await db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key,value))
        await db.commit()

async def admin_users(limit: int=50):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,))).fetchall()

async def admin_logs(limit: int=50):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))).fetchall()

async def admin_stats():
    async with connect() as db:
        users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        banned = (await (await db.execute("SELECT COUNT(*) FROM users WHERE banned=1")).fetchone())[0]
        premium = (await (await db.execute("SELECT COUNT(*) FROM users WHERE premium=1")).fetchone())[0]
        done = (await (await db.execute("SELECT COUNT(*) FROM downloads WHERE status='done'")).fetchone())[0]
        failed = (await (await db.execute("SELECT COUNT(*) FROM downloads WHERE status='error'")).fetchone())[0]
        mb = (await (await db.execute("SELECT COALESCE(SUM(size_mb),0) FROM downloads WHERE status='done'")).fetchone())[0]
        return dict(users=users,banned=banned,premium=premium,done=done,failed=failed,mb=float(mb or 0))


async def add_bookmark(user_id: int, url: str, title: str=''):
    async with connect() as db:
        cur = await db.execute("INSERT OR IGNORE INTO bookmarks(user_id,url,title) VALUES(?,?,?)", (user_id,url,title[:200]))
        await db.commit()
        return cur.lastrowid

async def list_bookmarks(user_id: int):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM bookmarks WHERE user_id=? ORDER BY id DESC LIMIT 30", (user_id,))).fetchall()

async def delete_bookmark(user_id: int, item_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM bookmarks WHERE user_id=? AND id=?", (user_id,item_id)); await db.commit()



async def failed_history(user_id: int, limit: int = 10):
    async with connect() as db:
        cur = await db.execute(
            "SELECT * FROM downloads WHERE user_id=? AND status='error' ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return await cur.fetchall()

async def duplicate_history(user_id: int, limit: int = 20):
    async with connect() as db:
        cur = await db.execute(
            """SELECT url, COUNT(*) AS total, MAX(id) AS last_id, MAX(created_at) AS last_created
               FROM downloads WHERE user_id=? GROUP BY url HAVING COUNT(*) > 1
               ORDER BY total DESC, last_id DESC LIMIT ?""",
            (user_id, limit),
        )
        return await cur.fetchall()

async def delete_failed_history(user_id: int):
    async with connect() as db:
        cur = await db.execute("DELETE FROM downloads WHERE user_id=? AND status='error'", (user_id,))
        await db.commit()
        return cur.rowcount

async def recent_downloads(limit: int=10):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limit,))).fetchall()


async def platform_stats(user_id: int):
    async with connect() as db:
        rows = await (await db.execute("""
            SELECT platform, COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),0) AS done,
                   COALESCE(SUM(CASE WHEN status='done' THEN size_mb ELSE 0 END),0) AS mb
            FROM downloads WHERE user_id=? GROUP BY platform ORDER BY done DESC, total DESC LIMIT 10
        """, (user_id,))).fetchall()
        return rows

async def clear_bookmarks(user_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM bookmarks WHERE user_id=?", (user_id,))
        await db.commit()

async def export_history(user_id: int, limit: int = 5000):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM downloads WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))).fetchall()

async def find_existing_download(user_id: int, url: str):
    async with connect() as db:
        return await (await db.execute(
            "SELECT * FROM downloads WHERE user_id=? AND url=? AND status='done' ORDER BY id DESC LIMIT 1",
            (user_id, url),
        )).fetchone()

async def failed_downloads(user_id: int, limit: int = 5):
    async with connect() as db:
        return await (await db.execute(
            "SELECT * FROM downloads WHERE user_id=? AND status='error' ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )).fetchall()



async def payment_summary():
    async with connect() as db:
        row = await (await db.execute("SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS stars, COUNT(DISTINCT user_id) AS payers FROM payments")).fetchone()
        return {'count': int(row['count'] or 0), 'stars': int(row['stars'] or 0), 'payers': int(row['payers'] or 0)}


async def create_schedule(user_id: int, chat_id: int, url: str, run_at: float, quality: str='720', fmt: str='mp4', template: str='clean', title: str=''):
    async with connect() as db:
        cur = await db.execute(
            "INSERT INTO scheduled_jobs(user_id,chat_id,url,run_at,quality,format,template,title) VALUES(?,?,?,?,?,?,?,?)",
            (user_id, chat_id, url, float(run_at), quality, fmt, template, title[:200])
        )
        await db.commit()
        return cur.lastrowid

async def load_scheduled_jobs():
    async with connect() as db:
        return await (await db.execute("SELECT * FROM scheduled_jobs ORDER BY run_at ASC")).fetchall()

async def list_scheduled(user_id: int):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM scheduled_jobs WHERE user_id=? ORDER BY run_at ASC", (user_id,))).fetchall()

async def delete_schedule(user_id: int, job_id: int) -> bool:
    async with connect() as db:
        cur = await db.execute("DELETE FROM scheduled_jobs WHERE user_id=? AND id=?", (user_id, job_id))
        await db.commit()
        return cur.rowcount > 0

async def claim_due_schedule(job_id: int) -> bool:
    async with connect() as db:
        cur = await db.execute("DELETE FROM scheduled_jobs WHERE id=?", (job_id,))
        await db.commit()
        return cur.rowcount > 0


async def init_next_schema():
    async with connect() as db:
        await db.executescript(NEXT_SCHEMA)
        await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('retry_max','3')")
        await db.commit()

async def collection_create(user_id:int,name:str):
    async with connect() as db:
        cur=await db.execute("INSERT OR IGNORE INTO collections(user_id,name) VALUES(?,?)",(user_id,name[:40])); await db.commit(); return cur.lastrowid
async def collection_list(user_id:int):
    async with connect() as db: return await (await db.execute("SELECT * FROM collections WHERE user_id=? ORDER BY name",(user_id,))).fetchall()
async def collection_add_bookmark(user_id:int,name:str,bookmark_id:int):
    async with connect() as db:
        row=await (await db.execute("SELECT id FROM collections WHERE user_id=? AND name=?",(user_id,name))).fetchone()
        if not row: return False
        await db.execute("INSERT OR IGNORE INTO collection_items(collection_id,bookmark_id) VALUES(?,?)",(row[0],bookmark_id)); await db.commit(); return True
async def collection_items(user_id:int,name:str):
    async with connect() as db: return await (await db.execute("SELECT b.* FROM bookmarks b JOIN collection_items ci ON ci.bookmark_id=b.id JOIN collections c ON c.id=ci.collection_id WHERE c.user_id=? AND c.name=? ORDER BY b.id DESC",(user_id,name))).fetchall()
async def collection_delete(user_id:int,name:str):
    async with connect() as db:
        row=await (await db.execute("SELECT id FROM collections WHERE user_id=? AND name=?",(user_id,name))).fetchone()
        if not row:return False
        await db.execute("DELETE FROM collection_items WHERE collection_id=?",(row[0],)); await db.execute("DELETE FROM collections WHERE id=?",(row[0],)); await db.commit(); return True
async def get_user_profile(user_id:int):
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_profiles(user_id) VALUES(?)",(user_id,)); await db.commit(); return await (await db.execute("SELECT * FROM user_profiles WHERE user_id=?",(user_id,))).fetchone()
async def set_filename_template(user_id:int,tpl:str):
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_profiles(user_id) VALUES(?)",(user_id,)); await db.execute("UPDATE user_profiles SET filename_template=? WHERE user_id=?",(tpl[:120],user_id)); await db.commit()
async def set_download_profile(user_id:int,profile:str):
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_profiles(user_id) VALUES(?)",(user_id,)); await db.execute("UPDATE user_profiles SET download_profile=? WHERE user_id=?",(profile,user_id)); await db.commit()
async def create_recurring(user_id:int,chat_id:int,url:str,cadence:str,hour:int,minute:int,weekday:int,quality:str,fmt:str,template:str):
    async with connect() as db:
        cur=await db.execute("INSERT INTO recurring_jobs(user_id,chat_id,url,cadence,hour,minute,weekday,quality,format,template) VALUES(?,?,?,?,?,?,?,?,?,?)",(user_id,chat_id,url,cadence,hour,minute,weekday,quality,fmt,template)); await db.commit(); return cur.lastrowid
async def list_recurring(user_id:int):
    async with connect() as db: return await (await db.execute("SELECT * FROM recurring_jobs WHERE user_id=? ORDER BY id DESC",(user_id,))).fetchall()
async def delete_recurring(user_id:int,rid:int):
    async with connect() as db:
        cur=await db.execute("DELETE FROM recurring_jobs WHERE user_id=? AND id=?",(user_id,rid)); await db.commit(); return cur.rowcount>0
async def list_retries(user_id:int,limit:int=20):
    async with connect() as db: return await (await db.execute("SELECT * FROM retry_jobs WHERE user_id=? ORDER BY id DESC LIMIT ?",(user_id,limit))).fetchall()
async def analytics_for_user(user_id:int):
    async with connect() as db:
        r=await (await db.execute("SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),0) done,COALESCE(SUM(size_mb),0) mb FROM downloads WHERE user_id=?",(user_id,))).fetchone(); top=await (await db.execute("SELECT platform,COUNT(*) n FROM downloads WHERE user_id=? GROUP BY platform ORDER BY n DESC LIMIT 5",(user_id,))).fetchall(); return {'total':int(r['total'] or 0),'done':int(r['done'] or 0),'mb':float(r['mb'] or 0),'top':[(x['platform'],int(x['n'])) for x in top]}
async def register_backup(path:str,size_mb:float):
    async with connect() as db: await db.execute("INSERT INTO backup_runs(path,size_mb) VALUES(?,?)",(path,size_mb)); await db.commit()
async def list_backups(limit:int=10):
    async with connect() as db: return await (await db.execute("SELECT * FROM backup_runs ORDER BY id DESC LIMIT ?",(limit,))).fetchall()

async def scheduled_count() -> int:
    async with connect() as db:
        return int((await (await db.execute("SELECT COUNT(*) FROM scheduled_jobs")).fetchone())[0])
