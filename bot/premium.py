
from .database import get_user, set_user_field

async def is_premium(user_id: int) -> bool:
    row = await get_user(user_id)
    return bool(row and row['premium'])

async def grant_premium(user_id: int, until: str | None = None):
    await set_user_field(user_id,'premium',1)
    await set_user_field(user_id,'premium_until',until)

async def revoke_premium(user_id: int):
    await set_user_field(user_id,'premium',0)
    await set_user_field(user_id,'premium_until',None)
