from __future__ import annotations

from .storage import find_existing_download

async def existing_download(user_id: int, url: str):
    return await find_existing_download(user_id, url)
