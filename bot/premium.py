from __future__ import annotations
from datetime import datetime, timezone
from .database import get_user, set_user_field


def _active(row) -> bool:
    if not row or not row['premium']:
        return False
    until = row['premium_until']
    if not until:
        return True
    try:
        dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except ValueError:
        return False


async def is_premium(user_id: int) -> bool:
    return _active(await get_user(user_id))


async def grant_premium(user_id: int, until: str | None = None):
    await set_user_field(user_id, 'premium', 1)
    await set_user_field(user_id, 'premium_until', until)


async def revoke_premium(user_id: int):
    await set_user_field(user_id, 'premium', 0)
    await set_user_field(user_id, 'premium_until', None)
