
from __future__ import annotations

from pathlib import Path
from typing import Any
import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / 'database' / 'ravenkai.db'

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
    notifications INTEGER DEFAULT 1
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
"""

async def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    async with await connect() as db:
        await db.executescript(SCHEMA)
        await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('maintenance','0')")
        await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('max_queue','2')")
        await db.commit()

async def ensure_user(user_id: int, name: str, username: str = ''):
    async with await connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id,name,username) VALUES(?,?,?)",
            (user_id, name, username or ''),
        )
        await db.execute(
            "UPDATE users SET name=?, username=?, last_seen=CURRENT_TIMESTAMP WHERE user_id=?",
            (name, username or '', user_id),
        )
        await db.commit()

async def get_user(user_id: int):
    async with await connect() as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()

async def set_user_field(user_id: int, field: str, value: Any):
    allowed = {'quality','format','auto_delete','notifications','premium','premium_until','banned'}
    if field not in allowed:
        raise ValueError('unsupported field')
    async with await connect() as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
        await db.commit()

async def record_download(user_id: int, url: str, platform: str, title: str, duration: int,
                          quality: str, fmt: str, size_mb: float, status: str='done', error: str=''):
    async with await connect() as db:
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
    async with await connect() as db:
        cur = await db.execute(
            "SELECT * FROM downloads WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        )
        return await cur.fetchall()

async def delete_history_item(user_id: int, item_id: int):
    async with await connect() as db:
        await db.execute("DELETE FROM downloads WHERE user_id=? AND id=?", (user_id,item_id))
        await db.commit()

async def clear_history(user_id: int):
    async with await connect() as db:
        await db.execute("DELETE FROM downloads WHERE user_id=?", (user_id,))
        await db.commit()

async def count_history(user_id: int):
    async with await connect() as db:
        row = await (await db.execute("SELECT COUNT(*) FROM downloads WHERE user_id=?", (user_id,))).fetchone()
        return int(row[0])

async def log_action(user_id: int | None, action: str, details: str=''):
    async with await connect() as db:
        await db.execute("INSERT INTO logs(user_id,action,details) VALUES(?,?,?)", (user_id,action,details[:1500]))
        await db.commit()

async def get_setting(key: str, default: str=''):
    async with await connect() as db:
        row = await (await db.execute("SELECT value FROM settings WHERE key=?", (key,))).fetchone()
        return row[0] if row else default

async def set_setting(key: str, value: str):
    async with await connect() as db:
        await db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key,value))
        await db.commit()

async def admin_users(limit: int=50):
    async with await connect() as db:
        return await (await db.execute("SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,))).fetchall()

async def admin_logs(limit: int=50):
    async with await connect() as db:
        return await (await db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))).fetchall()

async def admin_stats():
    async with await connect() as db:
        users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        banned = (await (await db.execute("SELECT COUNT(*) FROM users WHERE banned=1")).fetchone())[0]
        premium = (await (await db.execute("SELECT COUNT(*) FROM users WHERE premium=1")).fetchone())[0]
        done = (await (await db.execute("SELECT COUNT(*) FROM downloads WHERE status='done'")).fetchone())[0]
        failed = (await (await db.execute("SELECT COUNT(*) FROM downloads WHERE status='error'")).fetchone())[0]
        mb = (await (await db.execute("SELECT COALESCE(SUM(size_mb),0) FROM downloads WHERE status='done'")).fetchone())[0]
        return dict(users=users,banned=banned,premium=premium,done=done,failed=failed,mb=float(mb or 0))
