from .storage import analytics_for_user
async def summary(user_id:int): return await analytics_for_user(user_id)
