from __future__ import annotations

from .database import get_download, download_stats, search_history, failed_history, duplicate_history, delete_failed_history

async def repeat_download(user_id: int, item_id: int):
    row = await get_download(user_id, item_id)
    if not row:
        return None
    return dict(row)

async def personal_stats(user_id: int):
    return await download_stats(user_id)

async def find_downloads(user_id: int, query: str, limit: int = 10):
    rows = await search_history(user_id, query, limit)
    return [dict(r) for r in rows]


async def failed_items(user_id: int, limit: int = 10):
    rows = await failed_history(user_id, limit)
    return [dict(r) for r in rows]

async def duplicate_items(user_id: int, limit: int = 20):
    rows = await duplicate_history(user_id, limit)
    return [dict(r) for r in rows]

async def clear_failed_items(user_id: int):
    return await delete_failed_history(user_id)
