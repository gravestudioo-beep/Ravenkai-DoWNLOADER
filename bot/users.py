
from .database import ensure_user, get_user

async def register(tg_user):
    return await ensure_user(tg_user.id, tg_user.full_name or tg_user.username or 'Ravenkai', tg_user.username or '')

async def profile(user_id: int):
    return await get_user(user_id)
