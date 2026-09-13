from .storage import search_history
async def find(user_id:int,q:str,limit:int=20): return await search_history(user_id,q,limit)
