from __future__ import annotations
from .database import add_bookmark, list_bookmarks, delete_bookmark

async def save(user_id:int, url:str, title:str=''):
    return await add_bookmark(user_id,url,title)
async def all_for(user_id:int): return await list_bookmarks(user_id)
async def remove(user_id:int, item_id:int): return await delete_bookmark(user_id,item_id)
