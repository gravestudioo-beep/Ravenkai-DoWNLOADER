from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite


DB_PATH = Path(__file__).resolve().parent.parent / "database" / "ravenkai.db"


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


def connect() -> aiosqlite.Connection:
    """
    Возвращает неподключённое aiosqlite-соединение.

    Важно:
    НЕ использовать `await connect()`.
    Правильный вариант:
        async with connect() as db:
            ...
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row

    return db


async def init_db() -> None:
    """
    Создание таблиц и базовых настроек.
    """
    async with connect() as db:
        await db.executescript(SCHEMA)

        await db.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES('maintenance', '0')
            """
        )

        await db.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES('max_queue', '2')
            """
        )

        await db.commit()


async def ensure_user(
    user_id: int,
    name: str,
    username: str = "",
) -> None:
    async with connect() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users(
                user_id,
                name,
                username
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                name,
                username or "",
            ),
        )

        await db.execute(
            """
            UPDATE users
            SET
                name = ?,
                username = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (
                name,
                username or "",
                user_id,
            ),
        )

        await db.commit()


async def get_user(user_id: int):
    async with connect() as db:
        async with db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cur:
            return await cur.fetchone()


async def set_user_field(
    user_id: int,
    field: str,
    value: Any,
) -> None:
    allowed = {
        "quality",
        "format",
        "auto_delete",
        "notifications",
        "premium",
        "premium_until",
        "banned",
    }

    if field not in allowed:
        raise ValueError(f"unsupported field: {field}")

    async with connect() as db:
        await db.execute(
            f"""
            UPDATE users
            SET {field} = ?
            WHERE user_id = ?
            """,
            (
                value,
                user_id,
            ),
        )

        await db.commit()


async def record_download(
    user_id: int,
    url: str,
    platform: str,
    title: str,
    duration: int,
    quality: str,
    fmt: str,
    size_mb: float,
    status: str = "done",
    error: str = "",
) -> None:
    size_mb = float(size_mb or 0)

    async with connect() as db:
        await db.execute(
            """
            INSERT INTO downloads(
                user_id,
                url,
                platform,
                title,
                duration,
                quality,
                format,
                size_mb,
                status,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                url,
                platform or "",
                title or "",
                int(duration or 0),
                quality or "best",
                fmt or "mp4",
                size_mb,
                status or "done",
                error or "",
            ),
        )

        if status == "done":
            if fmt in {"mp3", "m4a", "audio"}:
                await db.execute(
                    """
                    UPDATE users
                    SET
                        audio = audio + 1,
                        downloaded_mb = downloaded_mb + ?
                    WHERE user_id = ?
                    """,
                    (
                        size_mb,
                        user_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    UPDATE users
                    SET
                        videos = videos + 1,
                        downloaded_mb = downloaded_mb + ?
                    WHERE user_id = ?
                    """,
                    (
                        size_mb,
                        user_id,
                    ),
                )

        await db.commit()


async def history(
    user_id: int,
    limit: int = 10,
    offset: int = 0,
):
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))

    async with connect() as db:
        async with db.execute(
            """
            SELECT *
            FROM downloads
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (
                user_id,
                limit,
                offset,
            ),
        ) as cur:
            return await cur.fetchall()


async def delete_history_item(
    user_id: int,
    item_id: int,
) -> None:
    async with connect() as db:
        await db.execute(
            """
            DELETE FROM downloads
            WHERE user_id = ?
              AND id = ?
            """,
            (
                user_id,
                item_id,
            ),
        )

        await db.commit()


async def clear_history(
    user_id: int,
) -> None:
    async with connect() as db:
        await db.execute(
            """
            DELETE FROM downloads
            WHERE user_id = ?
            """,
            (user_id,),
        )

        await db.commit()


async def count_history(
    user_id: int,
) -> int:
    async with connect() as db:
        async with db.execute(
            """
            SELECT COUNT(*)
            FROM downloads
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

    return int(row[0] if row else 0)


async def log_action(
    user_id: int | None,
    action: str,
    details: str = "",
) -> None:
    async with connect() as db:
        await db.execute(
            """
            INSERT INTO logs(
                user_id,
                action,
                details
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                action,
                (details or "")[:1500],
            ),
        )

        await db.commit()


async def get_setting(
    key: str,
    default: str = "",
) -> str:
    async with connect() as db:
        async with db.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (key,),
        ) as cur:
            row = await cur.fetchone()

    return row[0] if row else default


async def set_setting(
    key: str,
    value: str,
) -> None:
    async with connect() as db:
        await db.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (
                key,
                value,
            ),
        )

        await db.commit()


async def admin_users(
    limit: int = 50,
):
    limit = max(1, min(int(limit), 10000))

    async with connect() as db:
        async with db.execute(
            """
            SELECT *
            FROM users
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            return await cur.fetchall()


async def admin_logs(
    limit: int = 50,
):
    limit = max(1, min(int(limit), 10000))

    async with connect() as db:
        async with db.execute(
            """
            SELECT *
            FROM logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            return await cur.fetchall()


async def admin_stats() -> dict[str, Any]:
    async with connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users"
        ) as cur:
            users_row = await cur.fetchone()

        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE banned = 1"
        ) as cur:
            banned_row = await cur.fetchone()

        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE premium = 1"
        ) as cur:
            premium_row = await cur.fetchone()

        async with db.execute(
            "SELECT COUNT(*) FROM downloads WHERE status = 'done'"
        ) as cur:
            done_row = await cur.fetchone()

        async with db.execute(
            "SELECT COUNT(*) FROM downloads WHERE status = 'error'"
        ) as cur:
            failed_row = await cur.fetchone()

        async with db.execute(
            """
            SELECT COALESCE(SUM(size_mb), 0)
            FROM downloads
            WHERE status = 'done'
            """
        ) as cur:
            mb_row = await cur.fetchone()

    return {
        "users": int(users_row[0] if users_row else 0),
        "banned": int(banned_row[0] if banned_row else 0),
        "premium": int(premium_row[0] if premium_row else 0),
        "done": int(done_row[0] if done_row else 0),
        "failed": int(failed_row[0] if failed_row else 0),
        "mb": float(mb_row[0] if mb_row else 0),
    }
