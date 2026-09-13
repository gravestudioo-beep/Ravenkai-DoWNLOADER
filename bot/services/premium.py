from __future__ import annotations
from datetime import datetime, timezone, timedelta
from .storage import get_user, set_user_field


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
    if _active(await get_user(user_id)):
        return True
    from .storage import trial_active
    return await trial_active(user_id)

async def trial_remaining_days(user_id: int) -> int:
    from .storage import trial_days_left
    return await trial_days_left(user_id)


async def grant_premium(user_id: int, until: str | None = None):
    await set_user_field(user_id, 'premium', 1)
    await set_user_field(user_id, 'premium_until', until)

async def extend_premium_days(user_id: int, days: int):
    row = await get_user(user_id)
    now = datetime.now(timezone.utc)
    current = _parse_until(row['premium_until'] if row else None)
    base = current if current and current > now else now
    until = (base + timedelta(days=days)).isoformat()
    await grant_premium(user_id, until)
    return until

def _parse_until(until: str | None):
    if not until: return None
    try:
        dt = datetime.fromisoformat(until.replace('Z','+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def revoke_premium(user_id: int):
    await set_user_field(user_id, 'premium', 0)
    await set_user_field(user_id, 'premium_until', None)
