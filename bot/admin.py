
from __future__ import annotations
import os
from .database import admin_stats, admin_users, admin_logs, set_user_field

ADMINS = {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

async def stats(): return await admin_stats()
async def users(limit=30): return await admin_users(limit)
async def logs(limit=40): return await admin_logs(limit)
async def ban(user_id: int): await set_user_field(user_id,'banned',1)
async def unban(user_id: int): await set_user_field(user_id,'banned',0)
