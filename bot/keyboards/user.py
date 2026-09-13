from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎬 Видео', callback_data='menu:video'), InlineKeyboardButton(text='🎵 Аудио', callback_data='menu:audio')],
        [InlineKeyboardButton(text='📥 Очередь', callback_data='menu:queue'), InlineKeyboardButton(text='📁 История', callback_data='menu:history:0')],
        [InlineKeyboardButton(text='👤 Профиль', callback_data='menu:profile'), InlineKeyboardButton(text='🔖 Закладки', callback_data='menu:bookmarks')],
        [InlineKeyboardButton(text='⚙ Настройки', callback_data='menu:settings'), InlineKeyboardButton(text='⭐ Premium', callback_data='menu:premium')],
        [InlineKeyboardButton(text='🎬 Монтаж', callback_data='menu:montage'), InlineKeyboardButton(text='📊 Статистика', callback_data='menu:metrics')],
        [InlineKeyboardButton(text='🌙 О боте', callback_data='menu:about'), InlineKeyboardButton(text='💎 Тарифы', callback_data='menu:premium')],
    ])

def back():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Назад', callback_data='menu:home')]])

def quality_kb(job_id: str, audio=False, premium=False):
    if audio:
        rows = [[
            InlineKeyboardButton(text='🎵 MP3', callback_data=f'pick:f:{job_id}:mp3'),
            InlineKeyboardButton(text='🎧 M4A', callback_data=f'pick:f:{job_id}:m4a'),
        ], [InlineKeyboardButton(text='❌ Отмена', callback_data=f'job:cancel:{job_id}')]]
        return InlineKeyboardMarkup(inline_keyboard=rows)
    available = ['360', '480', '720', '1080'] + (['1440', '2160'] if premium else [])
    rows = [[InlineKeyboardButton(text=f'{q}p', callback_data=f'pick:q:{job_id}:{q}') for q in available[i:i+3]] for i in range(0, len(available), 3)]
    rows.append([InlineKeyboardButton(text='🏆 Лучшее', callback_data=f'pick:q:{job_id}:best')])
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data=f'job:cancel:{job_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def settings_kb(u):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'🎚 {u["quality"]}p', callback_data='set:quality'), InlineKeyboardButton(text=f'📦 {u["format"].upper()}', callback_data='set:format')],
        [InlineKeyboardButton(text=f'🧹 Автоудаление: {"ON" if u["auto_delete"] else "OFF"}', callback_data='set:auto')],
        [InlineKeyboardButton(text=f'🔔 Уведомления: {"ON" if u["notifications"] else "OFF"}', callback_data='set:notif')],
        [InlineKeyboardButton(text='↩️ Назад', callback_data='menu:home')],
    ])


def montage_kb(job_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔇 Без звука', callback_data=f'montage:{job_id}:mute'), InlineKeyboardButton(text='🎵 Только звук', callback_data=f'montage:{job_id}:audio')],
        [InlineKeyboardButton(text='📱 Вертикал 9:16', callback_data=f'montage:{job_id}:vertical'), InlineKeyboardButton(text='✂️ 30 секунд', callback_data=f'montage:{job_id}:short30')],
        [InlineKeyboardButton(text='🗜 Сжатие', callback_data=f'montage:{job_id}:compress'), InlineKeyboardButton(text='⬛ Квадрат 1:1', callback_data=f'montage:{job_id}:square')],
        [InlineKeyboardButton(text='✂️ 60 секунд', callback_data=f'montage:{job_id}:clip60'), InlineKeyboardButton(text='🖼 Кадр', callback_data=f'montage:{job_id}:thumbnail')],
        [InlineKeyboardButton(text='🐌 Slow 0.75×', callback_data=f'montage:{job_id}:slow'), InlineKeyboardButton(text='🎬 Оригинал', callback_data=f'montage:{job_id}:clean')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data=f'job:cancel:{job_id}')],
    ])

def plans_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⭐ 7 дней — 75 Stars', callback_data='pay:week')],
        [InlineKeyboardButton(text='⭐ 30 дней — 199 Stars', callback_data='pay:month')],
        [InlineKeyboardButton(text='⭐ 90 дней — 499 Stars', callback_data='pay:quarter')],
        [InlineKeyboardButton(text='↩️ Назад', callback_data='menu:home')],
    ])


def batch_quality_kb(batch_id: str, premium: bool = False):
    available = ['360', '480', '720', '1080'] + (['1440', '2160'] if premium else [])
    rows = [[InlineKeyboardButton(text=f'{q}p', callback_data=f'batch:q:{batch_id}:{q}') for q in available[i:i+3]] for i in range(0, len(available), 3)]
    rows.append([InlineKeyboardButton(text='🏆 Лучшее', callback_data=f'batch:q:{batch_id}:best')])
    rows.append([InlineKeyboardButton(text='❌ Отмена', callback_data=f'batch:cancel:{batch_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
