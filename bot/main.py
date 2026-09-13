
from __future__ import annotations
import asyncio, os, tempfile, shutil, time, uuid, logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand
from dotenv import load_dotenv

from .database import (
    init_db, ensure_user, get_user, history, clear_history, delete_history_item, count_history,
    record_download, log_action, get_setting, set_setting
)
from .downloader import run_download, extract_info
from .utils import platform, bar, esc, valid_url, human_bytes, human_duration, human_speed
from .admin import is_admin, stats, users, logs, ban, unban
from .premium import is_premium, grant_premium, revoke_premium
from .settings import QUALITY_OPTIONS, FORMAT_OPTIONS, AUDIO_FORMATS, set_setting as set_user_setting
from .queue import DownloadQueue, Job

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN: raise RuntimeError('BOT_TOKEN is not set')
MAX_MB = int(os.getenv('MAX_FILE_MB','49'))
PREMIUM_MAX_MB = int(os.getenv('PREMIUM_MAX_FILE_MB','95'))
CONCURRENCY = max(1, int(os.getenv('CONCURRENCY','2')))
DOWNLOAD_ROOT = Path(os.getenv('DOWNLOAD_DIR','downloads'))
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('ravenkai')
bot=Bot(TOKEN); dp=Dispatcher(); queue=DownloadQueue(CONCURRENCY)
pending: dict[str,dict] = {}
last_request: dict[int,float] = {}


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎬 Скачать видео', callback_data='menu:video'), InlineKeyboardButton(text='🎵 Скачать аудио', callback_data='menu:audio')],
        [InlineKeyboardButton(text='📥 Очередь', callback_data='menu:queue'), InlineKeyboardButton(text='📁 История', callback_data='menu:history:0')],
        [InlineKeyboardButton(text='👤 Профиль', callback_data='menu:profile'), InlineKeyboardButton(text='⚙ Настройки', callback_data='menu:settings')],
        [InlineKeyboardButton(text='⭐ Premium', callback_data='menu:premium'), InlineKeyboardButton(text='🌙 О боте', callback_data='menu:about')],
        [InlineKeyboardButton(text='🌙 БОТ СОЗДАН', callback_data='menu:creator')],
    ])

def back(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Назад',callback_data='menu:home')]])

def quality_kb(job_id: str, audio=False, premium=False):
    rows=[]
    available=['360','480','720','1080'] + (['1440','2160'] if premium else [])
    for i in range(0,len(available),3):
        rows.append([InlineKeyboardButton(text=f'{q}p',callback_data=f'pick:q:{job_id}:{q}') for q in available[i:i+3]])
    if not audio: rows.append([InlineKeyboardButton(text='🏆 Лучшее',callback_data=f'pick:q:{job_id}:best')])
    else: rows.append([InlineKeyboardButton(text='🎵 MP3',callback_data=f'pick:f:{job_id}:mp3'),InlineKeyboardButton(text='🎧 M4A',callback_data=f'pick:f:{job_id}:m4a')])
    rows.append([InlineKeyboardButton(text='❌ Отмена',callback_data=f'job:cancel:{job_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def settings_kb(u):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'🎚 Качество: {u["quality"]}p',callback_data='set:quality'), InlineKeyboardButton(text=f'📦 Формат: {u["format"].upper()}',callback_data='set:format')],
        [InlineKeyboardButton(text=f'🧹 Автоудаление: {"ON" if u["auto_delete"] else "OFF"}',callback_data='set:auto')],
        [InlineKeyboardButton(text=f'🔔 Уведомления: {"ON" if u["notifications"] else "OFF"}',callback_data='set:notif')],
        [InlineKeyboardButton(text='↩️ Назад',callback_data='menu:home')],
    ])

@dp.message(Command('start'))
async def start(m: Message):
    await ensure_user(m.from_user.id, m.from_user.full_name or 'Ravenkai', m.from_user.username or '')
    user=await get_user(m.from_user.id)
    if user['banned']: return await m.answer('⛔ Доступ к боту ограничен.')
    banner=Path('assets/pair_banner.png')
    text='🌙 <b>Ravenkai DOWNLOADER Ultra</b>\n\nБыстрый загрузчик видео, музыки и медиа.\n\nВыбери действие ниже.'
    if banner.exists(): await m.answer_photo(FSInputFile(banner), caption=text, reply_markup=main_menu())
    else: await m.answer(text, reply_markup=main_menu())

@dp.message(Command('help'))
async def help_cmd(m):
    await m.answer('<b>Ravenkai команды</b>\n/start — главное меню\n/history — история\n/profile — профиль\n/settings — настройки\n/premium — Premium\n/queue — очередь\n/cancel — отменить свои загрузки\n/id — твой Telegram ID\n/admin — админ-панель', reply_markup=main_menu())

@dp.message(Command('id'))
async def id_cmd(m): await m.answer(f'🪪 ID: <code>{m.from_user.id}</code>')
@dp.message(Command('profile'))
async def profile_cmd(m): await render_profile(m.from_user.id, m.chat.id, m)
@dp.message(Command('history'))
async def history_cmd(m): await render_history(m.from_user.id, m.chat.id, m, 0)
@dp.message(Command('settings'))
async def settings_cmd(m): await render_settings(m.from_user.id, m.chat.id, m)
@dp.message(Command('premium'))
async def premium_cmd(m): await render_premium(m.from_user.id, m.chat.id, m)

async def allowed_user(uid):
    row=await get_user(uid)
    return row and not row['banned']

async def render_profile(uid, chat_id, target):
    u=await get_user(uid)
    if not u: return
    text=(f'👤 <b>Профиль Ravenkai</b>\n\nID: <code>{u["user_id"]}</code>\n'
          f'Имя: {esc(u["name"])}\nВидео: {u["videos"]}\nАудио: {u["audio"]}\n'
          f'Скачано: {u["downloaded_mb"]:.1f} MB\nРегистрация: {u["registered_at"]}\n'
          f'Premium: {"⭐ Да" if u["premium"] else "Нет"}')
    if hasattr(target,'answer'): await target.answer(text,reply_markup=back())
    else: await bot.send_message(chat_id,text,reply_markup=back())

async def render_history(uid, chat_id, target, offset=0):
    rows=await history(uid,8,offset); total=await count_history(uid)
    text='📁 <b>История загрузок</b>\n\n'
    if not rows: text+='Пока пусто.'
    else:
        for x in rows:
            title=esc((x['title'] or x['url'])[:55])
            text += f'#{x["id"]} • {title}\n{x["platform"]} · {x["format"].upper()} · {x["size_mb"]:.1f} MB\n\n'
    rows_kb=[]
    for x in rows: rows_kb.append([InlineKeyboardButton(text=f'🗑 #{x["id"]}',callback_data=f'hist:del:{x["id"]}:{offset}')])
    nav=[]
    if offset>0: nav.append(InlineKeyboardButton(text='◀️',callback_data=f'menu:history:{max(0,offset-8)}'))
    if offset+8<total: nav.append(InlineKeyboardButton(text='▶️',callback_data=f'menu:history:{offset+8}'))
    if nav: rows_kb.append(nav)
    rows_kb.append([InlineKeyboardButton(text='🧹 Очистить историю',callback_data='hist:clear')])
    rows_kb.append([InlineKeyboardButton(text='↩️ Назад',callback_data='menu:home')])
    kb=InlineKeyboardMarkup(inline_keyboard=rows_kb)
    if hasattr(target,'edit_text'):
        try: await target.edit_text(text,reply_markup=kb)
        except Exception: await target.answer(text,reply_markup=kb)
    else: await target.answer(text,reply_markup=kb)

async def render_settings(uid, chat_id, target):
    u=await get_user(uid)
    text='<b>⚙ Настройки Ravenkai</b>\n\nКачество и формат будут сохранены для следующих загрузок.'
    if hasattr(target,'edit_text'):
        try: await target.edit_text(text,reply_markup=settings_kb(u))
        except Exception: await target.answer(text,reply_markup=settings_kb(u))
    else: await target.answer(text,reply_markup=settings_kb(u))

async def render_premium(uid, chat_id, target):
    yes=await is_premium(uid)
    text=('⭐ <b>Ravenkai Premium</b>\n\nСтатус: <b>АКТИВЕН</b>\n• 1440p / 4K\n• увеличенный лимит\n• приоритетная очередь\n• расширенные форматы' if yes else
          '⭐ <b>Ravenkai Premium</b>\n\nСтатус: <b>ОБЫЧНЫЙ</b>\n\nPremium открывает 1440p/4K, увеличенный лимит и приоритет очереди.')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⭐ Статус обновить',callback_data='premium:refresh')],[InlineKeyboardButton(text='↩️ Назад',callback_data='menu:home')]])
    if hasattr(target,'edit_text'):
        try: await target.edit_text(text,reply_markup=kb)
        except Exception: await target.answer(text,reply_markup=kb)
    else: await target.answer(text,reply_markup=kb)

@dp.message(Command('queue'))
async def queue_cmd(m):
    s=queue.snapshot(); await m.answer(f'📥 <b>Очередь</b>\n\nАктивно: {s["active"]}\nОжидают: {s["waiting"]}\nТвои задачи отменяются командой /cancel')

@dp.message(Command('cancel'))
async def cancel_cmd(m):
    n=queue.cancel_user(m.from_user.id); await m.answer(f'🛑 Отмечено на отмену: {n} задач.')

@dp.callback_query(F.data=='menu:home')
async def home(c): await c.message.edit_text('🌙 <b>Ravenkai DOWNLOADER Ultra</b>\n\nВыбери действие:',reply_markup=main_menu()); await c.answer()
@dp.callback_query(F.data=='menu:queue')
async def queue_menu(c):
    s=queue.snapshot(); await c.message.edit_text(f'📥 <b>Очередь</b>\n\nАктивно: {s["active"]}\nОжидают: {s["waiting"]}',reply_markup=back()); await c.answer()
@dp.callback_query(F.data=='menu:profile')
async def profile_cb(c): await render_profile(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data.startswith('menu:history:'))
async def history_cb(c): await render_history(c.from_user.id,c.message.chat.id,c,int(c.data.split(':')[-1])); await c.answer()
@dp.callback_query(F.data=='menu:settings')
async def settings_cb(c): await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='menu:premium')
async def premium_cb(c): await render_premium(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='menu:about')
async def about_cb(c):
    img=Path('assets/dark_fantasy_pair.png')
    cap='🌙 <b>Ravenkai DOWNLOADER Ultra</b>\n\nМедиа-бот на aiogram + yt-dlp + FFmpeg.\n\nИспользуй его только для контента, который тебе разрешено скачивать.'
    if img.exists(): await c.message.answer_photo(FSInputFile(img),caption=cap,reply_markup=back())
    else: await c.message.edit_text(cap,reply_markup=back())
    await c.answer()
@dp.callback_query(F.data=='menu:creator')
async def creator_cb(c):
    img=Path('assets/buttons/creator.png')
    text='🌙 <b>БОТ СОЗДАН</b>\n\nPpitchMoonWitch\'em\n\nв целях удивить его девушку/подругу «Нару»'
    if img.exists(): await c.message.answer_photo(FSInputFile(img),caption=text,reply_markup=back())
    else: await c.message.edit_text(text,reply_markup=back())
    await c.answer()

@dp.callback_query(F.data.in_({'menu:video','menu:audio'}))
async def choose_type(c):
    audio=c.data.endswith('audio'); pending[f'ask:{c.from_user.id}']={'audio':audio}
    await c.message.answer('🔗 Отправь ссылку на медиа одним сообщением.'); await c.answer()

@dp.message(F.text)
async def text_handler(m):
    if not await allowed_user(m.from_user.id): return await m.answer('⛔ Доступ ограничен.')
    text=m.text.strip()
    if not valid_url(text): return
    now=time.monotonic()
    if now-last_request.get(m.from_user.id,0)<2.0: return await m.answer('⏳ Подожди пару секунд перед следующей ссылкой.')
    last_request[m.from_user.id]=now
    ask=pending.pop(f'ask:{m.from_user.id}',{})
    audio=bool(ask.get('audio',False))
    try:
        info=await asyncio.to_thread(extract_info,text)
    except Exception as e:
        await log_action(m.from_user.id,'metadata_error',str(e)); return await m.answer(f'❌ Не удалось получить информацию.\n<code>{esc(e)}</code>')
    title=(info.get('title') or 'Без названия')[:90]; uploader=(info.get('uploader') or info.get('channel') or '—')[:70]
    duration=info.get('duration') or 0
    size=info.get('filesize') or info.get('filesize_approx') or 0
    jid=uuid.uuid4().hex[:10]
    pending[jid]={'user':m.from_user.id,'chat':m.chat.id,'url':text,'audio':audio,'title':title,'uploader':uploader,'duration':duration,'size':size}
    prem=await is_premium(m.from_user.id)
    card=(f'🔎 <b>{esc(title)}</b>\n\n👤 {esc(uploader)}\n⏱ {human_duration(duration)}\n'
          f'🌐 {platform(text)}\n💾 {human_bytes(size)}\n\n'
          f'{"🎵 Аудио" if audio else "🎬 Видео"}\nВыбери качество:')
    await m.answer(card,reply_markup=quality_kb(jid,audio,prem))

@dp.callback_query(F.data.startswith('pick:q:'))
async def pick_quality(c):
    _,_,jid,q=c.data.split(':'); p=pending.get(jid)
    if not p: return await c.answer('Ссылка устарела.',show_alert=True)
    if q in {'1440','2160'} and not await is_premium(c.from_user.id): return await c.answer('Это качество доступно Premium.',show_alert=True)
    p['quality']=q; p['fmt']='mp3' if p['audio'] else (await get_user(c.from_user.id))['format']
    job=Job(user_id=p['user'],chat_id=p['chat'],url=p['url'],quality=q,fmt=p['fmt'],audio=p['audio'],request_message_id=c.message.message_id,id=jid,meta=p)
    await queue.put(job); pending.pop(jid,None)
    await c.message.edit_text(f'📥 <b>Добавлено в очередь</b>\n\n{esc(p["title"])}\nКачество: <b>{q}</b>\nПозиция ожидает обработки…')
    await c.answer('Добавлено в очередь')

@dp.callback_query(F.data.startswith('pick:f:'))
async def pick_format(c):
    _,_,jid,fmt=c.data.split(':'); p=pending.get(jid)
    if not p: return await c.answer('Ссылка устарела.',show_alert=True)
    p['quality']='best'; p['fmt']=fmt
    job=Job(user_id=p['user'],chat_id=p['chat'],url=p['url'],quality='best',fmt=fmt,audio=True,request_message_id=c.message.message_id,id=jid,meta=p)
    await queue.put(job); pending.pop(jid,None); await c.message.edit_text(f'📥 Аудио <b>{fmt.upper()}</b> добавлено в очередь.'); await c.answer()

@dp.callback_query(F.data.startswith('job:cancel:'))
async def job_cancel(c):
    jid=c.data.split(':')[-1]; job=queue.by_id.get(jid)
    if job: job.cancelled=True; await c.answer('Загрузка отменена.')
    else: await c.answer('Задача уже завершена.',show_alert=True)

@dp.callback_query(F.data=='hist:clear')
async def clear_hist(c): await clear_history(c.from_user.id); await c.message.edit_text('🧹 История очищена.',reply_markup=back()); await c.answer()
@dp.callback_query(F.data.startswith('hist:del:'))
async def del_hist(c):
    _,_,item,offset=c.data.split(':'); await delete_history_item(c.from_user.id,int(item)); await render_history(c.from_user.id,c.message.chat.id,c,int(offset)); await c.answer('Удалено')

@dp.callback_query(F.data=='set:quality')
async def set_quality(c):
    rows=[[InlineKeyboardButton(text=f'{q}p',callback_data=f'setq:{q}') for q in QUALITY_OPTIONS[i:i+3]] for i in range(0,len(QUALITY_OPTIONS),3)]
    rows.append([InlineKeyboardButton(text='↩️ Назад',callback_data='menu:settings')]); await c.message.edit_text('🎚 Выбери качество по умолчанию:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()
@dp.callback_query(F.data.startswith('setq:'))
async def setq(c):
    q=c.data.split(':')[1]
    if q in {'1440','2160'} and not await is_premium(c.from_user.id): return await c.answer('Premium only',show_alert=True)
    await set_user_setting(c.from_user.id,'quality',q); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer('Сохранено')
@dp.callback_query(F.data=='set:format')
async def set_format(c):
    rows=[[InlineKeyboardButton(text=f.upper(),callback_data=f'setf:{f}') for f in FORMAT_OPTIONS]]+[ [InlineKeyboardButton(text='↩️ Назад',callback_data='menu:settings')] ]
    await c.message.edit_text('📦 Формат видео по умолчанию:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()
@dp.callback_query(F.data.startswith('setf:'))
async def setf(c): await set_user_setting(c.from_user.id,'format',c.data.split(':')[1]); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer('Сохранено')
@dp.callback_query(F.data=='set:auto')
async def set_auto(c):
    u=await get_user(c.from_user.id); await set_user_setting(c.from_user.id,'auto_delete',0 if u['auto_delete'] else 1); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='set:notif')
async def set_notif(c):
    u=await get_user(c.from_user.id); await set_user_setting(c.from_user.id,'notifications',0 if u['notifications'] else 1); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='premium:refresh')
async def premium_refresh(c): await render_premium(c.from_user.id,c.message.chat.id,c); await c.answer('Статус обновлён')

# Admin
@dp.message(Command('admin'))
async def admin_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    s=await stats(); await m.answer(f'👑 <b>Ravenkai Admin</b>\n\n/users\n/stats\n/logs\n/ban ID\n/unban ID\n/broadcast текст\n\nПользователей: {s["users"]}\nУспешных: {s["done"]}')
@dp.message(Command('stats'))
async def stats_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    s=await stats(); await m.answer(f'📊 Users: {s["users"]}\n🚫 Banned: {s["banned"]}\n⭐ Premium: {s["premium"]}\n✅ Done: {s["done"]}\n❌ Errors: {s["failed"]}\n💾 {s["mb"]:.1f} MB')
@dp.message(Command('users'))
async def users_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    rows=await users(40); text='👥 <b>Последние пользователи</b>\n\n'+'\n'.join(f'{r["user_id"]} · {esc(r["name"])} · {"BAN" if r["banned"] else "OK"} · {"PREM" if r["premium"] else "FREE"}' for r in rows)
    await m.answer(text[:4000])
@dp.message(Command('logs'))
async def logs_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    rows=await logs(30); text='🧾 <b>Логи</b>\n\n'+'\n'.join(f'#{r["id"]} {r["action"]} · {r["user_id"]} · {esc(r["details"][:90])}' for r in rows)
    await m.answer(text[:4000])
@dp.message(Command('ban'))
async def ban_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split();
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/ban ID')
    await ban(int(parts[1])); await m.answer('🚫 Пользователь заблокирован.')
@dp.message(Command('unban'))
async def unban_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split();
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/unban ID')
    await unban(int(parts[1])); await m.answer('✅ Разблокирован.')
@dp.message(Command('broadcast'))
async def broadcast_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer('/broadcast текст')
    from .database import admin_users
    rows=await admin_users(10000); ok=bad=0
    for r in rows:
        try: await bot.send_message(r['user_id'],parts[1]); ok+=1
        except Exception: bad+=1
        await asyncio.sleep(.05)
    await m.answer(f'📣 Готово. Доставлено: {ok}, ошибок: {bad}')

async def process_job(job: Job):
    uid=job.user_id
    if job.cancelled: return
    folder=Path(tempfile.mkdtemp(prefix=f'raven_{uid}_',dir=DOWNLOAD_ROOT))
    status='error'; size=0; info=job.meta or {}
    message=None
    try:
        message=await bot.send_message(job.chat_id,f'⚙️ Подготовка: <b>{esc(info.get("title","медиа"))}</b>')
        last_edit=0.0
        def hook(d):
            nonlocal last_edit
            if job.cancelled: raise KeyboardInterrupt()
            if d.get('status')=='downloading':
                now=time.monotonic()
                if now-last_edit<1.3: return
                last_edit=now
                total=d.get('total_bytes') or d.get('total_bytes_estimate') or 0; done=d.get('downloaded_bytes',0)
                pct=(done/total*100) if total else 0
                speed=human_speed(d.get('speed') or 0); eta=d.get('eta')
                asyncio.get_running_loop().create_task(message.edit_text(f'⬇️ <b>Ravenkai downloading</b>\n\n{bar(pct)} <b>{pct:.1f}%</b>\n⚡ {speed} · ⏱ {eta if eta is not None else "—"}s'))
        def cancelled(): return job.cancelled
        path,info=await asyncio.to_thread(run_download,job.url,folder,job.quality,job.audio,job.fmt,hook,cancelled)
        if job.cancelled: raise KeyboardInterrupt()
        size=path.stat().st_size/1024/1024
        u=await get_user(uid); limit=PREMIUM_MAX_MB if u and u['premium'] else MAX_MB
        if size>limit: raise RuntimeError(f'Файл {size:.1f} MB превышает лимит {limit} MB')
        if message: await message.edit_text('📤 Отправляю файл…')
        caption=(f'🌙 <b>Ravenkai DOWNLOADER Ultra</b>\n{esc(info.get("title",path.name)[:180])}\n'
                 f'🌐 {platform(job.url)} · {job.quality} · {job.fmt.upper()}\n💾 {size:.1f} MB')
        up=Path(path)
        file=FSInputFile(up)
        if job.audio: await bot.send_audio(job.chat_id,file,caption=caption)
        elif up.suffix.lower()=='.mp4': await bot.send_video(job.chat_id,file,caption=caption,supports_streaming=True)
        else: await bot.send_document(job.chat_id,file,caption=caption)
        status='done'
        await record_download(uid,job.url,platform(job.url),info.get('title',''),info.get('duration') or 0,job.quality,job.fmt,size,'done')
        if message: await message.edit_text('✅ <b>Готово!</b>')
        await log_action(uid,'download_done',f'{platform(job.url)} {size:.1f}MB')
    except KeyboardInterrupt:
        if message:
            try: await message.edit_text('🛑 Загрузка отменена.')
            except Exception: pass
        await record_download(uid,job.url,platform(job.url),info.get('title',''),info.get('duration') or 0,job.quality,job.fmt,size,'cancelled')
    except Exception as e:
        if message:
            try: await message.edit_text(f'❌ <b>Ошибка</b>\n<code>{esc(e)}</code>')
            except Exception: pass
        await record_download(uid,job.url,platform(job.url),info.get('title',''),info.get('duration') or 0,job.quality,job.fmt,size,'error',str(e))
        await log_action(uid,'download_error',str(e))
    finally:
        shutil.rmtree(folder,ignore_errors=True)

async def on_startup():
    await init_db()
    await queue.start(process_job)
    await bot.set_my_commands([
        BotCommand(command='start',description='Главное меню'),BotCommand(command='help',description='Помощь'),BotCommand(command='history',description='История'),
        BotCommand(command='profile',description='Профиль'),BotCommand(command='settings',description='Настройки'),BotCommand(command='premium',description='Premium'),
        BotCommand(command='queue',description='Очередь'),BotCommand(command='cancel',description='Отменить загрузки'),BotCommand(command='id',description='Мой ID')
    ])

async def main():
    await on_startup(); log.info('Ravenkai DOWNLOADER Ultra v3 started');
    try: await dp.start_polling(bot)
    finally: await queue.stop(); await bot.session.close()

if __name__=='__main__': asyncio.run(main())
