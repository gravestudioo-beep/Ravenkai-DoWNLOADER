from __future__ import annotations
from .database import get_download, history, list_bookmarks, delete_bookmark, clear_history

async def latest_download(user_id: int):
    rows = await history(user_id, 1, 0)
    return rows[0] if rows else None

async def bookmark_rows(user_id: int):
    return await list_bookmarks(user_id)

async def remove_bookmark(user_id: int, item_id: int):
    await delete_bookmark(user_id, item_id)
    return True

async def clear_user_history(user_id: int):
    await clear_history(user_id)
    return True
