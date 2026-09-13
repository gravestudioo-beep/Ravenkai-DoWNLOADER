
from __future__ import annotations
import os
from ..services.storage import admin_stats, admin_users, admin_logs, set_user_field

ADMINS = {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

async def stats(): return await admin_stats()
async def users(limit=30): return await admin_users(limit)
async def logs(limit=40): return await admin_logs(limit)
async def ban(user_id: int): await set_user_field(user_id,'banned',1)
async def unban(user_id: int): await set_user_field(user_id,'banned',0)


def admin_panel():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📊 Статистика', callback_data='admin:stats'), InlineKeyboardButton(text='👥 Пользователи', callback_data='admin:users')],
        [InlineKeyboardButton(text='📥 Очередь', callback_data='admin:queue'), InlineKeyboardButton(text='🧾 Платежи', callback_data='admin:payments')],
        [InlineKeyboardButton(text='💰 Stars', callback_data='admin:revenue'), InlineKeyboardButton(text='📣 Broadcast', callback_data='admin:broadcast')],
        [InlineKeyboardButton(text='🔧 Maintenance', callback_data='admin:maintenance'), InlineKeyboardButton(text='⏯ Queue', callback_data='admin:queuepause')],
        [InlineKeyboardButton(text='↩️ Закрыть', callback_data='admin:close')],
    ])
