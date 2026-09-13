from __future__ import annotations
import asyncio
import logging
import os
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand, BufferedInputFile, LabeledPrice
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import types
from dotenv import load_dotenv

from .services.storage import init_db, ensure_user, get_user, history, clear_history, delete_history_item, count_history, record_download, log_action, get_setting, set_setting, platform_stats, clear_bookmarks, export_history
from .services.downloader import run_download, extract_info
from .services.utils import platform, bar, esc, valid_url, human_duration, human_speed
from .handlers.admin import is_admin, stats, users, logs, ban, unban
from .services.premium import is_premium, trial_remaining_days, extend_premium_days, grant_premium
from .services.settings import QUALITY_OPTIONS, FORMAT_OPTIONS, set_setting as set_user_setting
from .services.job_queue import DownloadQueue, Job
from .services.security import validate_public_url
from .services.cache import InfoCache
from .services.cleanup import cleanup_loop
from .services.metrics import Metrics
from .services.bookmarks import save as save_bookmark, all_for, remove as remove_bookmark
from .services.user_tools import repeat_download, personal_stats, find_downloads, failed_items, duplicate_items, clear_failed_items
from .services.storage import failed_history
from .services.shortcuts import latest_download
from .services.montage import ffmpeg_transform, TEMPLATES
from .services.payments import PLANS, payload, parse_payload
from .services.scheduler import Scheduler, ScheduledJob
from .services.feature_store import init_feature_store
from .services.storage import init_next_schema
from .handlers.extra import router as extra_router
from .handlers.next_updates import router as next_updates_router
from .services.storage import record_payment, payment_history, trial_active, payment_summary, create_schedule, load_scheduled_jobs, list_scheduled, delete_schedule, claim_due_schedule, scheduled_count

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    raise RuntimeError('BOT_TOKEN is not set')
MAX_MB = int(os.getenv('MAX_FILE_MB', '49'))
PREMIUM_MAX_MB = int(os.getenv('PREMIUM_MAX_FILE_MB', '95'))
CONCURRENCY = max(1, int(os.getenv('CONCURRENCY', '2')))
PER_USER_QUEUE = max(1, int(os.getenv('PER_USER_QUEUE', '3')))
RATE_SECONDS = max(0.5, float(os.getenv('RATE_LIMIT_SECONDS', '2.0')))
DOWNLOAD_ROOT = Path(os.getenv('DOWNLOAD_DIR', 'downloads'))
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('ravenkai')
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(extra_router)
dp.include_router(next_updates_router)
queue = DownloadQueue(CONCURRENCY, PER_USER_QUEUE)
pending: dict[str, dict] = {}
last_request: dict[int, float] = {}
info_cache = InfoCache(DOWNLOAD_ROOT / '.info_cache', ttl=int(os.getenv('INFO_CACHE_TTL', '900')))
metrics = Metrics(time.monotonic())


from .services.ux import existing_download

async def get_user_download(user_id: int, item_id: int):
    from .services.storage import get_download
    row = await get_download(user_id, item_id)
    return row
cleanup_task: asyncio.Task | None = None
scheduler = Scheduler(float(os.getenv('SCHEDULE_POLL_SECONDS','1.5')))


from .keyboards.user import main_menu, back, quality_kb, settings_kb, montage_kb, plans_kb, batch_quality_kb


async def allowed_user(uid: int):
    row = await get_user(uid)
    return bool(row and not row['banned'])


async def render_profile(uid, chat_id, target):
    u = await get_user(uid)
    if not u: return
    prem = await is_premium(uid)
    text = (f'👤 <b>Профиль Ravenkai</b>\n\nID: <code>{u["user_id"]}</code>\n'
            f'Имя: {esc(u["name"])}\nВидео: {u["videos"]}\nАудио: {u["audio"]}\n'
            f'Скачано: {u["downloaded_mb"]:.1f} MB\nPremium: {"⭐ АКТИВЕН" if prem else "FREE"}')
    await (target.answer(text, reply_markup=back()) if hasattr(target, 'answer') else bot.send_message(chat_id, text, reply_markup=back()))


async def render_history(uid, chat_id, target, offset=0):
    rows = await history(uid, 8, offset); total = await count_history(uid)
    text = '📁 <b>История загрузок</b>\n\n'
    if not rows: text += 'Пока пусто.'
    else:
        for x in rows:
            text += f'#{x["id"]} • {esc((x["title"] or x["url"])[:50])}\n{x["platform"]} · {x["format"].upper()} · {x["size_mb"]:.1f} MB\n\n'
    kb = [[InlineKeyboardButton(text=f'🗑 #{x["id"]}', callback_data=f'hist:del:{x["id"]}:{offset}')] for x in rows]
    nav=[]
    if offset>0: nav.append(InlineKeyboardButton(text='◀️',callback_data=f'menu:history:{max(0,offset-8)}'))
    if offset+8<total: nav.append(InlineKeyboardButton(text='▶️',callback_data=f'menu:history:{offset+8}'))
    if nav: kb.append(nav)
    kb += [[InlineKeyboardButton(text='🧹 Очистить',callback_data='hist:clear')],[InlineKeyboardButton(text='↩️ Назад',callback_data='menu:home')]]
    markup=InlineKeyboardMarkup(inline_keyboard=kb)
    try: await target.edit_text(text, reply_markup=markup)
    except Exception: await target.answer(text, reply_markup=markup)


async def render_settings(uid, chat_id, target):
    u=await get_user(uid); markup=settings_kb(u)
    text='<b>⚙ Настройки Ravenkai</b>\n\nПараметры применяются к новым задачам.'
    try: await target.edit_text(text,reply_markup=markup)
    except Exception: await target.answer(text,reply_markup=markup)


async def render_premium(uid, chat_id, target):
    yes=await is_premium(uid)
    trial_left=await trial_remaining_days(uid)
    if yes and trial_left:
        text=f'⭐ <b>Premium 6.1</b>\n\nСтатус: <b>TRIAL</b>\nОсталось: <b>{trial_left} дн.</b>\n\nПосле пробного периода можно купить Premium за Telegram Stars.'
    elif yes:
        u=await get_user(uid)
        text=f'⭐ <b>Premium 6.1</b>\n\nСтатус: <b>АКТИВЕН</b>\nДо: <b>{esc(str(u["premium_until"]))}</b>\n\n• 1440p / 4K\n• повышенный лимит\n• приоритет очереди\n• шаблоны монтажа'
    else:
        text='⭐ <b>Premium 6.1</b>\n\nСтатус: <b>FREE</b>\n\nЕсть 3-дневный пробный период Premium для новых пользователей.\nПосле него — тарифы за Telegram Stars.'
    markup=plans_kb()
    try: await target.edit_text(text,reply_markup=markup)
    except Exception: await target.answer(text,reply_markup=markup)


@dp.message(Command('start'))
async def start(m: Message):
    await ensure_user(m.from_user.id, m.from_user.full_name or 'Ravenkai', m.from_user.username or '')
    if not await allowed_user(m.from_user.id): return await m.answer('⛔ Доступ к боту ограничен.')
    banner=Path(__file__).resolve().parent.parent / 'assets' / 'pair_banner.png'
    text='🌙 <b>Ravenkai DOWNLOADER Ultra 8.2</b>\n\n⚡ Priority Queue · 🛡 Safe URLs · 🎬 Шаблоны монтажа\n🧪 Новым пользователям — 3 дня Premium\n\nВыбери действие ниже.'
    if banner.exists(): await m.answer_photo(FSInputFile(banner),caption=text,reply_markup=main_menu())
    else: await m.answer(text,reply_markup=main_menu())


@dp.message(Command('help'))
async def help_cmd(m): await m.answer('<b>Ravenkai 7.2</b>\n/start · /history · /search · /repeat · /again · /mystats · /top · /export · /jsonexport · /info · /forget · /bookmark · /profile · /settings · /premium · /queue · /cancel · /id · /health · /bookmarks · /clearbookmarks · /failed · /duplicates · /last · /cancelall · /failedretry · /privacy · /montage · /batch · /schedule · /schedules · /schedule_cancel · /trial · /admin')
@dp.message(Command('id'))
async def id_cmd(m): await m.answer(f'🪪 ID: <code>{m.from_user.id}</code>')
@dp.message(Command('profile'))
async def profile_cmd(m): await render_profile(m.from_user.id,m.chat.id,m)
@dp.message(Command('history'))
async def history_cmd(m): await render_history(m.from_user.id,m.chat.id,m,0)
@dp.message(Command('settings'))
async def settings_cmd(m): await render_settings(m.from_user.id,m.chat.id,m)
@dp.message(Command('bookmarks'))
async def bookmarks_cmd(m):
    rows=await all_for(m.from_user.id)
    if not rows: return await m.answer('🔖 Закладок пока нет.')
    text='🔖 <b>Мои закладки</b>\n\n' + '\n'.join(f'#{r["id"]} · {esc((r["title"] or r["url"])[:70])}' for r in rows)
    kb=[[InlineKeyboardButton(text='▶️ Открыть',callback_data=f'bookmark:go:{r["id"]}'), InlineKeyboardButton(text='🗑',callback_data=f'bookmark:del:{r["id"]}')] for r in rows]
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
@dp.message(Command('save'))
async def save_cmd(m):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2 or not valid_url(parts[1]): return await m.answer('Использование: /save https://...')
    await save_bookmark(m.from_user.id, parts[1].strip(), '')
    await m.answer('🔖 Ссылка сохранена в закладки.')
def _parse_delay(value: str) -> int | None:
    import re
    m = re.fullmatch(r'(\d+)\s*([smhd]?)', (value or '').strip().lower())
    if not m: return None
    n=int(m.group(1)); unit=m.group(2) or 'm'
    mult={'s':1,'m':60,'h':3600,'d':86400}[unit]
    seconds=n*mult
    return seconds if 30 <= seconds <= 7*86400 else None

@dp.message(Command('schedule'))
async def schedule_cmd(m):
    parts=(m.text or '').split(maxsplit=2)
    if len(parts)<3:
        return await m.answer('⏰ Использование: <code>/schedule 30m https://...</code>\nДопустимо от 30 секунд до 7 дней.')
    delay=_parse_delay(parts[1])
    if delay is None: return await m.answer('❌ Интервал: 30s–7d.')
    ok,reason=validate_public_url(parts[2].strip())
    if not ok: return await m.answer(f'❌ {esc(reason)}')
    if not await allowed_user(m.from_user.id): return await m.answer('⛔ Доступ ограничен.')
    u=await get_user(m.from_user.id); quality=u['quality'] if u else '720'; fmt=u['format'] if u else 'mp4'
    run_at=time.time()+delay
    sid=await create_schedule(m.from_user.id,m.chat.id,parts[2].strip(),run_at,quality,fmt,'clean','Плановая загрузка')
    scheduler.add(ScheduledJob(id=sid,user_id=m.from_user.id,chat_id=m.chat.id,url=parts[2].strip(),run_at=run_at,quality=quality,fmt=fmt,template='clean',title='Плановая загрузка'))
    await m.answer(f'⏰ <b>Запланировано #{sid}</b>\nЗапуск: <b>{time.strftime("%d.%m %H:%M",time.localtime(run_at))}</b>\nКачество: {esc(quality)}p')

@dp.message(Command('schedules'))
async def schedules_cmd(m):
    rows=await list_scheduled(m.from_user.id)
    if not rows: return await m.answer('⏰ Планировщик пуст.')
    lines=['⏰ <b>Запланированные загрузки</b>','']
    kb=[]
    for r in rows:
        lines.append(f'#{r["id"]} · {time.strftime("%d.%m %H:%M",time.localtime(float(r["run_at"]))) } · {esc(r["url"][:70])}')
        kb.append([InlineKeyboardButton(text=f'🗑 Отменить #{r["id"]}',callback_data=f'schedule:cancel:{r["id"]}')])
    await m.answer('\n'.join(lines),reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(Command('schedule_cancel'))
async def schedule_cancel_cmd(m):
    parts=(m.text or '').split()
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/schedule_cancel ID')
    sid=int(parts[1]); ok=await delete_schedule(m.from_user.id,sid); scheduler.cancel(sid)
    await m.answer('✅ Удалено.' if ok else '❌ Задача не найдена.')

@dp.callback_query(F.data.startswith('schedule:cancel:'))
async def schedule_cancel_cb(c):
    sid=int(c.data.split(':')[-1])
    ok=await delete_schedule(c.from_user.id,sid); scheduler.cancel(sid)
    await c.answer('Отменено.' if ok else 'Уже отменено.',show_alert=not ok)
    if ok: await schedules_cmd(c.message)

@dp.message(Command('premium'))
async def premium_cmd(m): await render_premium(m.from_user.id,m.chat.id,m)
@dp.message(Command('health'))
async def health_cmd(m):
    s=queue.snapshot(); sc=await scheduled_count(); await m.answer(f'🟢 <b>Ravenkai 7.2</b>\nWorkers: {CONCURRENCY}\nActive: {s["active"]}\nWaiting: {s["waiting"]}\nScheduled: {sc}\nQueue: {"PAUSED" if s["paused"] else "RUNNING"}')
@dp.message(Command('queue'))
async def queue_cmd(m):
    s=queue.snapshot(); mine=queue.user_pending_count(m.from_user.id)
    await m.answer(f'📥 <b>Очередь</b>\n\nАктивно: {s["active"]}\nОжидают: {s["waiting"]}\nТвои задачи: {mine}/{PER_USER_QUEUE}\nСтатус: {"⏸ пауза" if s["paused"] else "▶️ работает"}')
@dp.message(Command('cancel'))
async def cancel_cmd(m): await m.answer(f'🛑 Отмечено на отмену: {queue.cancel_user(m.from_user.id)} задач.')

@dp.message(Command('mystats'))
async def mystats_cmd(m):
    x = await personal_stats(m.from_user.id)
    await m.answer(
        f'📊 <b>Моя статистика</b>\n\n'
        f'Всего задач: <b>{x.get("total",0)}</b>\n'
        f'✅ Успешно: <b>{x.get("done",0)}</b>\n'
        f'❌ Ошибки: <b>{x.get("failed",0)}</b>\n'
        f'🛑 Отменено: <b>{x.get("cancelled",0)}</b>\n'
        f'🎬 Видео: <b>{x.get("video",0)}</b>\n'
        f'🎵 Аудио: <b>{x.get("audio",0)}</b>\n'
        f'💾 Объём: <b>{float(x.get("mb",0) or 0):.1f} MB</b>')

@dp.message(Command('search'))
async def search_cmd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2: return await m.answer('Использование: /search название или сайт')
    rows = await find_downloads(m.from_user.id, parts[1])
    if not rows: return await m.answer('🔎 Ничего не найдено.')
    await m.answer('🔎 <b>Результаты</b>\n\n' + '\n'.join(f'#{r["id"]} · {esc((r["title"] or r["url"])[:70])}' for r in rows))

@dp.message(Command('failed'))
async def failed_cmd(m):
    rows = await failed_items(m.from_user.id, 10)
    if not rows:
        return await m.answer('✅ Ошибочных загрузок нет.')
    lines = ['❌ <b>Последние ошибки</b>', '']
    kb = []
    for r in rows:
        title = esc((r.get('title') or r.get('url') or 'Медиа')[:55])
        err = esc((r.get('error') or 'неизвестная ошибка')[:90])
        lines.append(f'#{r["id"]} · {title}\n<code>{err}</code>')
        kb.append([InlineKeyboardButton(text=f'🔁 Повторить #{r["id"]}', callback_data=f'retryid:{r["id"]}')])
    kb.append([InlineKeyboardButton(text='🧹 Очистить ошибки', callback_data='failed:clear')])
    await m.answer('\n\n'.join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(Command('jsonexport'))
async def jsonexport_cmd(m):
    rows = await export_history(m.from_user.id)
    payload = []
    for r in rows:
        payload.append({k: r[k] for k in r.keys()})
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    await m.answer_document(BufferedInputFile(data, filename='ravenkai-history.json'), caption=f'🧾 JSON экспорт: {len(payload)} записей')

@dp.message(Command('info'))
async def info_cmd(m):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2 or not parts[1].isdigit():
        return await m.answer('Использование: /info ID')
    row=await repeat_download(m.from_user.id, int(parts[1]))
    if not row:
        return await m.answer('❌ Запись не найдена.')
    await m.answer(
        f'🔎 <b>Загрузка #{row["id"]}</b>\n\n'
        f'Название: <b>{esc((row["title"] or "—")[:180])}</b>\n'
        f'🌐 {esc(row["platform"] or "unknown")}\n'
        f'📦 {esc(row["format"] or "—")} · {esc(row["quality"] or "—")}\n'
        f'💾 {float(row["size_mb"] or 0):.2f} MB\n'
        f'⏱ {int(row["duration"] or 0)} сек.\n'
        f'📌 Статус: <b>{esc(row["status"] or "—")}</b>\n'
        f'🕒 {esc(row["created_at"] or "—")}\n\n'
        f'🔗 {esc(row["url"] or "—")}',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔖 В закладки', callback_data=f'history:bookmark:{row["id"]}'), InlineKeyboardButton(text='🗑 Забыть', callback_data=f'history:forget:{row["id"]}')],
            [InlineKeyboardButton(text='🔁 Повторить', callback_data=f'retryid:{row["id"]}')]
        ]))

@dp.message(Command('forget'))
async def forget_cmd(m):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2 or not parts[1].isdigit():
        return await m.answer('Использование: /forget ID')
    row=await repeat_download(m.from_user.id, int(parts[1]))
    if not row:
        return await m.answer('❌ Запись не найдена.')
    await m.answer(f'🗑 Удалить запись <b>#{row["id"]}</b>?', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Удалить', callback_data=f'history:forget:{row["id"]}'), InlineKeyboardButton(text='↩️ Отмена', callback_data='history:forget_cancel')]]))

@dp.message(Command('bookmark'))
async def bookmark_cmd(m):
    parts=m.text.split(maxsplit=1)
    if len(parts)<2 or not parts[1].isdigit():
        return await m.answer('Использование: /bookmark ID')
    row=await repeat_download(m.from_user.id, int(parts[1]))
    if not row:
        return await m.answer('❌ Запись не найдена.')
    await save_bookmark(m.from_user.id, row['url'], row['title'] or '')
    await m.answer(f'🔖 Запись <b>#{row["id"]}</b> добавлена в закладки.')

@dp.message(Command('privacy'))
async def privacy_cmd(m):
    await m.answer('🔐 <b>О данных</b>\n\nСостояние бота и история хранятся локально в <code>data/ravenkai.db</code>. Отдельная внешняя БД не используется.')

@dp.message(Command('duplicates'))
async def duplicates_cmd(m):
    rows = await duplicate_items(m.from_user.id, 20)
    if not rows:
        return await m.answer('✅ Дубликатов в истории не найдено.')
    text = '♻️ <b>Дубликаты в истории</b>\n\n'
    for r in rows:
        text += f'• {esc((r["url"] or "")[:75])} — <b>{r["total"]}</b> записей\n'
    await m.answer(text)

@dp.message(Command('clearbookmarks'))
async def clearbookmarks_cmd(m):
    await clear_bookmarks(m.from_user.id)
    await m.answer('🧹 Закладки очищены.')

@dp.message(Command('top'))
async def top_cmd(m):
    rows = await platform_stats(m.from_user.id)
    if not rows:
        return await m.answer('📊 Пока недостаточно данных для рейтинга.')
    text='🏆 <b>Твои платформы</b>\n\n'
    for i,r in enumerate(rows,1):
        text += f'{i}. <b>{esc(r["platform"] or "unknown")}</b> — {r["done"]} готово · {float(r["mb"] or 0):.1f} MB\n'
    await m.answer(text)

@dp.message(Command('export'))
async def export_cmd(m):
    rows = await export_history(m.from_user.id)
    if not rows:
        return await m.answer('📄 История пока пуста.')
    import csv, io
    out=io.StringIO()
    writer=csv.writer(out)
    writer.writerow(['id','url','platform','title','duration','quality','format','size_mb','status','error','created_at'])
    for r in rows:
        writer.writerow([r['id'],r['url'],r['platform'],r['title'],r['duration'],r['quality'],r['format'],r['size_mb'],r['status'],r['error'],r['created_at']])
    data=out.getvalue().encode('utf-8-sig')
    await m.answer_document(BufferedInputFile(data, filename='ravenkai-history.csv'), caption=f'📄 Экспортировано записей: {len(rows)}')

@dp.message(Command('repeat'))
async def repeat_cmd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit(): return await m.answer('Использование: /repeat ID')
    row = await repeat_download(m.from_user.id, int(parts[1]))
    if not row: return await m.answer('❌ Запись не найдена.')
    ok, reason = validate_public_url(row['url'])
    if not ok: return await m.answer(f'❌ Ссылка больше не разрешена: {reason}')
    prem = await is_premium(m.from_user.id)
    jid = uuid.uuid4().hex[:10]
    pending[jid] = {'user':m.from_user.id,'chat':m.chat.id,'url':row['url'],'audio':row['format'] in {'mp3','m4a'},'title':row['title'] or 'Медиа','duration':row['duration'] or 0,'fmt':row['format'] or 'mp4'}
    await m.answer(f'🔁 <b>Повтор #{row["id"]}</b>\n\n{esc(row["title"] or row["url"])}\n\nВыбери параметры:', reply_markup=quality_kb(jid, pending[jid]['audio'], prem))




@dp.message(Command('again'))
async def again_cmd(m):
    row = await latest_download(m.from_user.id)
    if not row:
        return await m.answer('🕘 У тебя пока нет загрузок.')
    ok, reason = validate_public_url(row['url'])
    if not ok:
        return await m.answer(f'❌ Ссылка больше не разрешена: {reason}')
    prem = await is_premium(m.from_user.id)
    jid = uuid.uuid4().hex[:10]
    audio = (row['format'] or '').lower() in {'mp3', 'm4a', 'audio'}
    pending[jid] = {
        'user': m.from_user.id,
        'chat': m.chat.id,
        'url': row['url'],
        'audio': audio,
        'title': row['title'] or 'Медиа',
        'duration': row['duration'] or 0,
        'fmt': row['format'] or ('mp3' if audio else 'mp4'),
        'created': time.monotonic(),
    }
    await m.answer(
        f'🔁 <b>Повтор последней загрузки #{row["id"]}</b>\n\n'
        f'{esc(row["title"] or row["url"])}\n\nВыбери параметры:',
        reply_markup=quality_kb(jid, audio, prem),
    )


@dp.message(Command('last'))
async def last_cmd(m):
    row = await latest_download(m.from_user.id)
    if not row:
        return await m.answer('🕘 У тебя пока нет загрузок.')
    status = row['status']
    text = (f'🕘 <b>Последняя загрузка</b>\n\n'
            f'#{row["id"]} · {esc((row["title"] or row["url"])[:100])}\n'
            f'🌐 {esc(row["platform"] or "unknown")}\n'
            f'📦 {row["format"].upper()} · {row["quality"]}\n'
            f'💾 {float(row["size_mb"] or 0):.1f} MB\n'
            f'Статус: <b>{esc(status)}</b>')
    kb=[[InlineKeyboardButton(text='🔁 Повторить',callback_data=f'retryid:{row["id"]}')]]
    if row['url']:
        kb.append([InlineKeyboardButton(text='🔗 Открыть источник',url=row['url'])])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(Command('cancelall'))
async def cancelall_cmd(m):
    count = queue.cancel_user(m.from_user.id)
    await m.answer(f'🛑 Отмечено на отмену: <b>{count}</b> задач.')

@dp.message(Command('failedretry'))
async def failedretry_cmd(m):
    rows = await failed_history(m.from_user.id, 5)
    if not rows:
        return await m.answer('✅ Ошибок для повтора нет.')
    created = []
    available = max(0, PER_USER_QUEUE - queue.user_pending_count(m.from_user.id))
    prem = await is_premium(m.from_user.id)
    for row in rows[:available]:
        ok, _ = validate_public_url(row['url'])
        if not ok:
            continue
        jid = uuid.uuid4().hex[:10]
        audio = row['format'] in {'mp3','m4a','audio'}
        pending[jid] = {'user':m.from_user.id,'chat':m.chat.id,'url':row['url'],'audio':audio,'title':row['title'] or 'Медиа','duration':row['duration'] or 0,'fmt':row['format'] or ('mp3' if audio else 'mp4'),'created':time.monotonic()}
        created.append((jid, row))
    if not created:
        return await m.answer('⚠️ Нет доступных ошибок для повтора.')
    for jid, row in created:
        await m.answer(
            f'🔁 <b>Повтор #{row["id"]}</b>\n{esc((row["title"] or row["url"])[:100])}\n\nВыбери параметры:',
            reply_markup=quality_kb(jid, row['format'] in {'mp3','m4a','audio'}, prem)
        )

@dp.message(Command('batch'))
async def batch_cmd(m):
    raw=(m.text or '').splitlines()[1:]
    raw='\n'.join(raw).strip()
    if not raw:
        return await m.answer('📦 <b>Пакетная загрузка</b>\n\nОтправь /batch и ниже от 2 до 5 публичных ссылок, по одной на строку.')
    urls=[x.strip() for x in raw.splitlines() if x.strip()]
    if not 2 <= len(urls) <= 5:
        return await m.answer('📦 Нужно от 2 до 5 ссылок.')
    good=[]
    for url in urls:
        ok, reason=validate_public_url(url)
        if not ok:
            return await m.answer(f'❌ Ссылка недоступна: {esc(reason)}')
        if queue.has_duplicate(m.from_user.id,url):
            continue
        good.append(url)
    if not good:
        return await m.answer('⚠️ Все ссылки уже находятся в твоей очереди.')
    bid=uuid.uuid4().hex[:10]
    pending[f'batch:{bid}']={'user':m.from_user.id,'chat':m.chat.id,'urls':good,'created':time.monotonic()}
    await m.answer(f'📦 <b>Пакет: {len(good)} ссылок</b>\n\nВыбери качество для всех задач:', reply_markup=batch_quality_kb(bid, await is_premium(m.from_user.id)))

@dp.message(Command('montage'))
async def montage_cmd(m):
    await m.answer('🎬 <b>Шаблоны монтажа 6.2</b>\n\n🔇 без звука · 🎵 MP3 · 📱 9:16 · ✂️ 30 сек · ✂️ 60 сек · 🗜 сжатие · ⬛ 1:1 · 🐌 0.75× · 🖼 кадр-превью\n\nОткрой «🎬 Монтаж» и пришли ссылку.')

@dp.message(Command('trial'))
async def trial_cmd(m):
    days=await trial_remaining_days(m.from_user.id)
    await m.answer(f'🧪 <b>Пробный период</b>\n\nОсталось: <b>{days} дн.</b>')

@dp.callback_query(F.data=='menu:premium')
async def premium_cb2(c): await render_premium(c.from_user.id,c.message.chat.id,c); await c.answer()

@dp.callback_query(F.data=='menu:montage')
async def montage_menu(c):
    await begin_mode(c, audio=False, montage=True)

@dp.callback_query(F.data.startswith('pay:'))
async def pay_cb(c):
    plan=c.data.split(':',1)[1]
    cfg=PLANS.get(plan)
    if not cfg or not cfg['stars']:
        return await c.answer('Недоступно', show_alert=True)
    p=payload(plan,c.from_user.id)
    await bot.send_invoice(c.message.chat.id, title=cfg['title'], description=f'Ravenkai Premium на {cfg["days"]} дней', payload=p, currency='XTR', prices=[LabeledPrice(label=cfg['title'], amount=cfg['stars'])])
    await c.answer()

@dp.pre_checkout_query()
async def pre_checkout(q):
    plan, uid=parse_payload(q.invoice_payload)
    if not plan or uid != q.from_user.id:
        return await q.answer(ok=False, error_message='Некорректный счёт.')
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(m):
    sp=m.successful_payment
    plan, uid=parse_payload(sp.invoice_payload)
    if not plan or uid != m.from_user.id:
        return await m.answer('⚠️ Платёж получен, но payload не распознан. Проверь журнал.')
    cfg=PLANS[plan]
    await record_payment(uid, sp.invoice_payload, sp.total_amount, sp.currency, sp.telegram_payment_charge_id, 'premium', cfg['days'])
    until=await extend_premium_days(uid,cfg['days'])
    await m.answer(f'✅ <b>Оплата прошла</b>\n\n⭐ Premium продлён на <b>{cfg["days"]} дней</b>.\nДо: <b>{esc(until)}</b>')

@dp.callback_query(F.data=='menu:home')
async def home(c): await c.message.edit_text('🌙 <b>Ravenkai DOWNLOADER Ultra 8.2</b>\n\nВыбери действие:',reply_markup=main_menu()); await c.answer()
@dp.callback_query(F.data=='menu:queue')
async def queue_menu(c):
    s=queue.snapshot(); mine=queue.user_pending_count(c.from_user.id)
    await c.message.edit_text(f'📥 <b>Очередь</b>\n\nАктивно: {s["active"]}\nОжидают: {s["waiting"]}\nТвои: {mine}/{PER_USER_QUEUE}\n\nПриоритет Premium обрабатывается раньше обычных задач.',reply_markup=back()); await c.answer()
@dp.callback_query(F.data=='menu:profile')
async def profile_cb(c): await render_profile(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data.startswith('menu:history:'))
async def history_cb(c): await render_history(c.from_user.id,c.message.chat.id,c,int(c.data.split(':')[-1])); await c.answer()
@dp.callback_query(F.data=='menu:bookmarks')
async def bookmarks_cb(c):
    rows=await all_for(c.from_user.id)
    if not rows: return await c.message.edit_text('🔖 <b>Закладки</b>\n\nПока пусто.',reply_markup=back())
    text='🔖 <b>Закладки</b>\n\n' + '\n'.join(f'#{r["id"]} · {esc((r["title"] or r["url"])[:70])}' for r in rows)
    kb=[[InlineKeyboardButton(text='▶️ Открыть',callback_data=f'bookmark:go:{r["id"]}'), InlineKeyboardButton(text='🗑',callback_data=f'bookmark:del:{r["id"]}')] for r in rows]
    kb.append([InlineKeyboardButton(text='↩️ Назад',callback_data='menu:home')])
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)); await c.answer()
@dp.callback_query(F.data.startswith('bookmark:go:'))
async def bookmark_go_cb(c):
    item = int(c.data.split(':')[-1])
    rows = await all_for(c.from_user.id)
    row = next((r for r in rows if int(r['id']) == item), None)
    if not row:
        return await c.answer('Закладка не найдена.', show_alert=True)
    ok, reason = validate_public_url(row['url'])
    if not ok:
        return await c.answer(reason, show_alert=True)
    jid = uuid.uuid4().hex[:10]
    pending[jid] = {'user':c.from_user.id,'chat':c.message.chat.id,'url':row['url'],'audio':False,'title':row['title'] or 'Медиа'}
    await c.message.edit_text(f'🔖 <b>{esc(row["title"] or row["url"])}</b>\n\nВыбери качество:', reply_markup=quality_kb(jid, False, await is_premium(c.from_user.id)))
    await c.answer()

@dp.callback_query(F.data.startswith('bookmark:del:'))
async def bookmark_del_cb(c):
    await remove_bookmark(c.from_user.id,int(c.data.split(':')[-1])); await bookmarks_cb(c)
@dp.callback_query(F.data=='menu:metrics')
async def metrics_cb(c):
    x=metrics.snapshot(); await c.message.edit_text(f'📊 <b>Ravenkai Metrics</b>\n\nUptime: {x["uptime"]}s\n✅ Done: {x["completed"]}\n❌ Errors: {x["failed"]}\n🛑 Cancelled: {x["cancelled"]}\n📤 Sent: {x["gb"]:.2f} GB',reply_markup=back()); await c.answer()
@dp.callback_query(F.data=='menu:settings')
async def settings_cb(c): await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='premium:refresh')
async def premium_refresh_old(c): await render_premium(c.from_user.id,c.message.chat.id,c); await c.answer('Обновлено')
@dp.callback_query(F.data=='menu:about')
async def about_cb(c): await c.message.edit_text('🌙 <b>Ravenkai DOWNLOADER Ultra 8.2</b>\n\naiogram + yt-dlp + FFmpeg\n\nСкачивай только контент, на который у тебя есть право.',reply_markup=back()); await c.answer()
@dp.callback_query(F.data=='menu:creator')
async def creator_cb(c): await c.message.edit_text('🖤 <b>Ravenkai 7.2</b>\n\nНовая очередь, live-progress, безопасная валидация URL и расширенная админка.',reply_markup=back()); await c.answer()


async def begin_mode(c, audio=False, montage=False):
    pending[f'chat:{c.from_user.id}']={'audio':audio,'montage':montage,'created':time.monotonic()}
    label='аудио' if audio else 'видео'
    if montage:
        label='видео для монтажа'
    await c.message.edit_text(f'🔗 Пришли ссылку на {label}.\n\nПосле этого бот покажет предпросмотр и доступные шаблоны.',reply_markup=back()); await c.answer()

@dp.callback_query(F.data=='menu:video')
async def video_cb(c): await begin_mode(c,False)
@dp.callback_query(F.data=='menu:audio')
async def audio_cb(c): await begin_mode(c,True)


@dp.message(F.text)
async def url_message(m: Message):
    uid=m.from_user.id
    # Drop stale interactive sessions so old buttons cannot accumulate forever.
    now_m=time.monotonic()
    for _k,_v in list(pending.items()):
        if isinstance(_v,dict) and _v.get('created') and now_m-_v['created'] > 900:
            pending.pop(_k,None)
    if not await allowed_user(uid): return await m.answer('⛔ Доступ ограничен.')
    value=(m.text or '').strip()
    ok, reason = validate_public_url(value)
    if not ok: return await m.answer(f'❌ {reason}')
    now=time.monotonic()
    if now-last_request.get(uid,0) < RATE_SECONDS: return await m.answer('⏳ Слишком часто. Подожди немного.')
    last_request[uid]=now
    if queue.has_duplicate(uid,value): return await m.answer('⚠️ Такая ссылка уже есть у тебя в очереди.')
    previous = await existing_download(uid, value)
    if previous:
        kb = [[InlineKeyboardButton(text=f'🔁 Повторить #{previous["id"]}', callback_data=f'retryid:{previous["id"]}')],
              [InlineKeyboardButton(text='🔗 Открыть источник', url=value)]]
        return await m.answer(
            f'✅ <b>Ты уже скачивал эту ссылку</b>\n\n{esc((previous["title"] or value)[:120])}\n'
            f'Последний успешный результат: #{previous["id"]} · {float(previous["size_mb"] or 0):.1f} MB',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    settings=await get_user(uid)
    mode=pending.get(f'chat:{uid}',{})
    audio=mode.get('audio',False)
    montage_mode=mode.get('montage',False)
    jid=uuid.uuid4().hex[:10]
    pending[jid]={'user':uid,'chat':m.chat.id,'url':value,'audio':audio,'title':'Медиа','created':time.monotonic(),'montage_mode':montage_mode}
    try:
        info=info_cache.get(value) or await asyncio.to_thread(extract_info,value)
        info_cache.set(value, info)
        pending[jid].update({'title':info.get('title') or 'Медиа','duration':info.get('duration') or 0,'uploader':info.get('uploader') or ''})
        txt=f'🔎 <b>{esc(info.get("title") or "Медиа")}</b>\n\n🌐 {platform(value)}\n👤 {esc(info.get("uploader") or "—")}\n⏱ {human_duration(info.get("duration") or 0)}\n\nВыбери режим:'
        prem=await is_premium(uid)
        if montage_mode and not audio:
            await m.answer(txt+'\n\n🎬 <b>Выбери шаблон монтажа:</b>',reply_markup=montage_kb(jid))
        else:
            await m.answer(txt,reply_markup=quality_kb(jid,audio,prem))
    except Exception as e:
        pending.pop(jid,None)
        await m.answer(f'❌ Не удалось получить данные ссылки.\n<code>{esc(str(e))}</code>')


@dp.callback_query(F.data.startswith('batch:cancel:'))
async def batch_cancel(c):
    bid=c.data.split(':')[-1]
    pending.pop(f'batch:{bid}',None)
    await c.message.edit_text('🛑 Пакет отменён.', reply_markup=back())
    await c.answer('Отменено')

@dp.callback_query(F.data.startswith('batch:q:'))
async def batch_pick(c):
    _,_,bid,q=c.data.split(':')
    p=pending.get(f'batch:{bid}')
    if not p: return await c.answer('Пакет устарел.', show_alert=True)
    if q in {'1440','2160'} and not await is_premium(c.from_user.id):
        return await c.answer('Только Premium.', show_alert=True)
    urls=list(p['urls'])
    available=max(0, PER_USER_QUEUE-queue.user_pending_count(c.from_user.id))
    if not available:
        return await c.answer('Твой лимит очереди уже заполнен.', show_alert=True)
    urls=urls[:available]
    premium=await is_premium(c.from_user.id)
    for idx,url in enumerate(urls,1):
        jid=uuid.uuid4().hex[:10]
        meta={'title':f'Пакет {idx}/{len(urls)}','batch_id':bid,'batch_index':idx,'batch_total':len(urls),'created':time.monotonic()}
        job=Job(user_id=c.from_user.id,chat_id=c.message.chat.id,url=url,quality=q,fmt='mp4',audio=False,request_message_id=c.message.message_id,id=jid,priority=0 if premium else 10,meta=meta)
        try:
            await queue.put(job)
        except Exception:
            break
    pending.pop(f'batch:{bid}',None)
    await c.message.edit_text(f'📦 <b>Пакет запущен</b>\n\nДобавлено задач: <b>{len(urls)}</b>\nКачество: <b>{esc(q)}</b>', reply_markup=back())
    await c.answer('Пакет добавлен')

@dp.callback_query(F.data.startswith('montage:'))
async def montage_pick(c):
    _,jid,template=c.data.split(':',2); p=pending.get(jid)
    if not p: return await c.answer('Ссылка устарела.',show_alert=True)
    p['template']=template
    if template=='audio':
        p['audio']=True; p['fmt']='mp3'; p['quality']='best'
    await c.message.edit_text(f'🎬 Шаблон: <b>{esc(TEMPLATES[template][0])}</b>\n\nТеперь выбери качество:', reply_markup=quality_kb(jid, p.get('audio',False), await is_premium(c.from_user.id)))
    await c.answer('Шаблон выбран')

@dp.callback_query(F.data.startswith('pick:q:'))
async def pick_quality(c):
    _,_,jid,q=c.data.split(':'); p=pending.get(jid)
    if not p: return await c.answer('Ссылка устарела.',show_alert=True)
    if p.get('audio'): return await c.answer('Для аудио выбери MP3 или M4A.', show_alert=True)
    if q in {'1440','2160'} and not await is_premium(c.from_user.id): return await c.answer('Доступно только Premium.',show_alert=True)
    p['quality']=q; p['fmt']='mp4'
    job=Job(user_id=p['user'],chat_id=p['chat'],url=p['url'],quality=q,fmt='mp4',audio=p['audio'],request_message_id=c.message.message_id,id=jid,priority=0 if await is_premium(p['user']) else 10,meta=p)
    try: await queue.put(job)
    except Exception as e: return await c.answer(str(e),show_alert=True)
    pending.pop(jid,None)
    await c.message.edit_text(f'📥 <b>Задача #{jid}</b> добавлена.\n\n{esc(p["title"])}\nКачество: <b>{q}</b>\nПозиция: {queue.position(jid) or 1}',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🛑 Отменить',callback_data=f'job:cancel:{jid}')]]))
    await c.answer('Добавлено')


@dp.callback_query(F.data.startswith('pick:f:'))
async def pick_format(c):
    _,_,jid,fmt=c.data.split(':'); p=pending.get(jid)
    if not p: return await c.answer('Ссылка устарела.',show_alert=True)
    p.update({'quality':'best','fmt':fmt,'audio':True})
    job=Job(user_id=p['user'],chat_id=p['chat'],url=p['url'],quality='best',fmt=fmt,audio=True,request_message_id=c.message.message_id,id=jid,priority=0 if await is_premium(p['user']) else 10,meta=p)
    try: await queue.put(job)
    except Exception as e: return await c.answer(str(e),show_alert=True)
    pending.pop(jid,None); await c.message.edit_text(f'📥 Аудио <b>{fmt.upper()}</b> добавлено в очередь.'); await c.answer('Добавлено')

@dp.callback_query(F.data.startswith('retry:'))
async def retry_cb(c):
    jid = c.data.split(':',1)[1]
    # The current in-memory job may be gone; use the most recent history entry as a safe retry source.
    row = await latest_download(c.from_user.id)
    if not row:
        return await c.answer('Нет загрузки для повтора.', show_alert=True)
    ok, reason = validate_public_url(row['url'])
    if not ok:
        return await c.answer(reason, show_alert=True)
    new_id = uuid.uuid4().hex[:10]
    pending[new_id] = {'user':c.from_user.id,'chat':c.message.chat.id,'url':row['url'],'audio':row['format'] in {'mp3','m4a'},'title':row['title'] or 'Медиа','duration':row['duration'] or 0,'fmt':row['format'] or 'mp4'}
    await c.message.edit_text('🔁 Выбери параметры для повторной загрузки:', reply_markup=quality_kb(new_id, pending[new_id]['audio'], await is_premium(c.from_user.id)))
    await c.answer('Повтор создан')

@dp.callback_query(F.data.startswith('job:cancel:'))
async def job_cancel(c):
    jid=c.data.split(':')[-1]
    if queue.cancel_job(jid,c.from_user.id): await c.answer('Отмена запрошена.')
    else: await c.answer('Задача уже завершена.',show_alert=True)


@dp.callback_query(F.data.startswith('retryid:'))
async def retry_history_item(c):
    item_id = int(c.data.split(':')[1])
    row = await get_user_download(c.from_user.id, item_id)
    if not row:
        return await c.answer('Запись не найдена.', show_alert=True)
    ok, reason = validate_public_url(row['url'])
    if not ok:
        return await c.answer(reason, show_alert=True)
    new_id = uuid.uuid4().hex[:10]
    audio = row['format'] in {'mp3','m4a'}
    pending[new_id] = {'user':c.from_user.id,'chat':c.message.chat.id,'url':row['url'],'audio':audio,'title':row['title'] or 'Медиа','duration':row['duration'] or 0,'fmt':row['format'] or 'mp4'}
    await c.message.edit_text('🔁 Выбери параметры для повторной загрузки:', reply_markup=quality_kb(new_id, audio, await is_premium(c.from_user.id)))
    await c.answer('Повтор создан')

@dp.callback_query(F.data=='failed:clear')
async def clear_failed_cb(c):
    count = await clear_failed_items(c.from_user.id)
    await c.message.edit_text(f'🧹 Удалено ошибочных записей: <b>{count}</b>.', reply_markup=back())
    await c.answer()

@dp.callback_query(F.data.startswith('history:bookmark:'))
async def history_bookmark_cb(c):
    item_id=int(c.data.split(':')[-1]); row=await repeat_download(c.from_user.id,item_id)
    if not row: return await c.answer('Запись не найдена.',show_alert=True)
    await save_bookmark(c.from_user.id,row['url'],row['title'] or '')
    await c.answer('🔖 Добавлено в закладки')

@dp.callback_query(F.data=='history:forget_cancel')
async def history_forget_cancel(c):
    await c.answer('Отмена')

@dp.callback_query(F.data.startswith('history:forget:'))
async def history_forget_cb(c):
    item_id=int(c.data.split(':')[-1])
    await delete_history_item(c.from_user.id,item_id)
    try: await c.message.edit_text(f'🗑 Запись <b>#{item_id}</b> удалена.')
    except Exception: pass
    await c.answer('Удалено')

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
    if q in {'1440','2160'} and not await is_premium(c.from_user.id): return await c.answer('Только Premium.',show_alert=True)
    await set_user_setting(c.from_user.id,'quality',q); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer('Сохранено')
@dp.callback_query(F.data=='set:format')
async def set_format(c):
    rows=[[InlineKeyboardButton(text=f.upper(),callback_data=f'setf:{f}') for f in FORMAT_OPTIONS],[InlineKeyboardButton(text='↩️ Назад',callback_data='menu:settings')]]; await c.message.edit_text('📦 Формат видео:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()
@dp.callback_query(F.data.startswith('setf:'))
async def setf(c): await set_user_setting(c.from_user.id,'format',c.data.split(':')[1]); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer('Сохранено')
@dp.callback_query(F.data=='set:auto')
async def set_auto(c):
    u=await get_user(c.from_user.id); await set_user_setting(c.from_user.id,'auto_delete',0 if u['auto_delete'] else 1); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='set:notif')
async def set_notif(c):
    u=await get_user(c.from_user.id); await set_user_setting(c.from_user.id,'notifications',0 if u['notifications'] else 1); await render_settings(c.from_user.id,c.message.chat.id,c); await c.answer()
@dp.callback_query(F.data=='premium:refresh')
async def premium_refresh(c): await render_premium(c.from_user.id,c.message.chat.id,c); await c.answer('Обновлено')


# Admin
@dp.callback_query(F.data.startswith('admin:'))
async def admin_panel_cb(c):
    if not is_admin(c.from_user.id): return await c.answer('Нет доступа', show_alert=True)
    action=c.data.split(':',1)[1]
    if action=='close':
        await c.message.edit_text('👑 Панель закрыта.', reply_markup=back()); return await c.answer()
    if action=='stats':
        s=await stats(); q=queue.snapshot(); text=f'📊 <b>Admin 6.1</b>\n\nUsers: {s["users"]}\nPremium: {s["premium"]}\nDone: {s["done"]}\nErrors: {s["failed"]}\nQueue: {q["active"]}/{q["waiting"]}'
    elif action=='users':
        rows=await users(25); text='👥 <b>Пользователи</b>\n\n'+'\n'.join(f'{r["user_id"]} · {esc(r["name"])} · {"BAN" if r["banned"] else "OK"} · {"PREM" if r["premium"] else "FREE"}' for r in rows)[:3900]
    elif action=='queue':
        q=queue.snapshot(); text=f'📥 <b>Очередь</b>\n\nActive: {q["active"]}\nWaiting: {q["waiting"]}\nPaused: {q["paused"]}'
    elif action=='payments':
        rows=await payment_history(20); text='💎 <b>Платежи</b>\n\n' + ('\n'.join(f'#{r["id"]} · {r["user_id"]} · {r["amount"]} {r["currency"]} · {r["days"]}d' for r in rows) or 'Платежей нет.')
    elif action=='revenue':
        x=await payment_summary(); text=f'💰 <b>Доход Stars</b>\n\nПлатежей: {x["count"]}\nПлательщиков: {x["payers"]}\nВсего: <b>{x["stars"]} Stars</b>'
    elif action=='broadcast':
        text='📣 <b>Broadcast</b>\n\nИспользуй команду <code>/broadcast текст</code> для отправки сообщения всем активным пользователям.'
    elif action=='maintenance':
        cur=await get_setting('maintenance','0'); new='0' if cur=='1' else '1'; await set_setting('maintenance',new); text=f'🔧 Maintenance: <b>{"ON" if new=="1" else "OFF"}</b>'
    elif action=='queuepause':
        queue.paused=not queue.paused; text=f'📥 Queue pause: <b>{"ON" if queue.paused else "OFF"}</b>'
    else: text='Неизвестное действие.'
    await c.message.edit_text(text, reply_markup=__import__('bot.handlers.admin',fromlist=['admin_panel']).admin_panel()); await c.answer()

@dp.message(Command('admin'))
async def admin_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    s=await stats(); from .handlers.admin import admin_panel; await m.answer(f'👑 <b>Admin 6.1</b>\n\nUsers: {s["users"]} · Done: {s["done"]}', reply_markup=admin_panel())
@dp.message(Command('stats'))
async def stats_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    s=await stats(); q=queue.snapshot(); await m.answer(f'📊 Users: {s["users"]}\n🚫 Banned: {s["banned"]}\n⭐ Premium: {s["premium"]}\n✅ Done: {s["done"]}\n❌ Errors: {s["failed"]}\n💾 {s["mb"]:.1f} MB\n📥 Active: {q["active"]} · Waiting: {q["waiting"]}')
@dp.message(Command('users'))
async def users_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    rows=await users(40); await m.answer('👥 <b>Users</b>\n\n'+'\n'.join(f'{r["user_id"]} · {esc(r["name"])} · {"BAN" if r["banned"] else "OK"} · {"PREM" if r["premium"] else "FREE"}' for r in rows)[:4000])
@dp.message(Command('logs'))
async def logs_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    rows=await logs(30); await m.answer('🧾 <b>Logs</b>\n\n'+'\n'.join(f'#{r["id"]} {r["action"]} · {r["user_id"]} · {esc(r["details"][:90])}' for r in rows)[:4000])
@dp.message(Command('ban'))
async def ban_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split();
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/ban ID')
    await ban(int(parts[1])); queue.cancel_user(int(parts[1])); await m.answer('🚫 Заблокирован и задачи отменены.')
@dp.message(Command('unban'))
async def unban_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split();
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/unban ID')
    await unban(int(parts[1])); await m.answer('✅ Разблокирован.')
@dp.message(Command('maintenance'))
async def maintenance_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split(maxsplit=1); mode=parts[1].lower() if len(parts)>1 else ''
    if mode not in {'on','off'}: return await m.answer('/maintenance on|off')
    await set_setting('maintenance','1' if mode=='on' else '0'); await m.answer(f'🔧 Maintenance: {mode.upper()}')
@dp.message(Command('queue_pause'))
async def queue_pause_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split(maxsplit=1); mode=parts[1].lower() if len(parts)>1 else ''
    if mode not in {'on','off'}: return await m.answer('/queue_pause on|off')
    queue.paused=(mode=='on'); await m.answer(f'📥 Queue paused: {queue.paused}')
@dp.message(Command('broadcast'))
async def broadcast_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split(maxsplit=1)
    if len(parts)<2: return await m.answer('/broadcast текст')
    from .services.storage import admin_users
    rows=await admin_users(10000); ok=bad=0
    for r in rows:
        try: await bot.send_message(r['user_id'],parts[1]); ok+=1
        except Exception: bad+=1
        await asyncio.sleep(.04)
    await m.answer(f'📣 Доставлено: {ok}, ошибок: {bad}')


@dp.message(Command('revenue'))
async def revenue_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    x=await payment_summary()
    await m.answer(f'💰 <b>Stars</b>\n\nПлатежей: {x["count"]}\nПлательщиков: {x["payers"]}\nВсего: <b>{x["stars"]} Stars</b>')

@dp.message(Command('user'))
async def user_cmd(m):
    if not is_admin(m.from_user.id): return await m.answer('⛔ Нет доступа.')
    parts=m.text.split()
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/user ID')
    u=await get_user(int(parts[1]))
    if not u: return await m.answer('Пользователь не найден.')
    await m.answer(f'👤 <b>Пользователь</b>\n\nID: <code>{u["user_id"]}</code>\nИмя: {esc(u["name"])}\nUsername: @{esc(u["username"] or "—")}\nВидео: {u["videos"]}\nАудио: {u["audio"]}\nPremium: {"ON" if await is_premium(u["user_id"]) else "OFF"}\nPremium до: {esc(str(u["premium_until"] or "—"))}\nСкачано: {float(u["downloaded_mb"] or 0):.1f} MB')

@dp.message(Command('grant'))
async def grant_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split()
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/grant ID [days]')
    days=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 30
    until=await extend_premium_days(int(parts[1]),days)
    await m.answer(f'✅ Premium выдан на {days} дн. до {esc(until)}')

@dp.message(Command('revoke'))
async def revoke_cmd(m):
    if not is_admin(m.from_user.id): return
    parts=m.text.split()
    if len(parts)<2 or not parts[1].isdigit(): return await m.answer('/revoke ID')
    from .services.premium import revoke_premium
    await revoke_premium(int(parts[1])); await m.answer('🛑 Premium отключён.')

async def process_job(job: Job):
    uid=job.user_id
    folder=Path(tempfile.mkdtemp(prefix=f'raven_{uid}_',dir=DOWNLOAD_ROOT))
    status='error'; size=0; info=job.meta or {}; message=None
    try:
        maintenance=await get_setting('maintenance','0')
        if maintenance and not is_admin(uid): raise RuntimeError('Бот находится на техническом обслуживании.')
        message=await bot.send_message(job.chat_id,f'⚙️ Подготовка: <b>{esc(info.get("title","медиа"))}</b>')
        last_edit=0.0
        def hook(d):
            nonlocal last_edit
            if job.cancelled: raise KeyboardInterrupt()
            if d.get('status')=='downloading':
                now=time.monotonic()
                if now-last_edit<1.2: return
                last_edit=now
                total=d.get('total_bytes') or d.get('total_bytes_estimate') or 0; done=d.get('downloaded_bytes',0); pct=(done/total*100) if total else 0
                speed=human_speed(d.get('speed') or 0); eta=d.get('eta')
                text=f'⬇️ <b>Загрузка</b>\n\n{bar(pct)} <b>{pct:.1f}%</b>\n⚡ {speed} · ⏱ {eta if eta is not None else "—"}s\n\nID: <code>{job.id}</code>'
                asyncio.get_running_loop().create_task(message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🛑 Отменить',callback_data=f'job:cancel:{job.id}')]])))
        transient_errors = ('timed out','timeout','temporarily','temporary','connection','network','http error 429','http error 5','unable to download webpage','urlopen error')
        last_exc = None
        for attempt in range(1, 4):
            try:
                path,download_info=await asyncio.to_thread(run_download,job.url,folder,job.quality,job.audio,job.fmt,hook,lambda:job.cancelled)
                info={**(job.meta or {}), **(download_info or {})}
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if job.cancelled: raise KeyboardInterrupt()
                if attempt >= 3 or not any(token in msg for token in transient_errors):
                    raise
                await asyncio.sleep(attempt * 2)
        if last_exc is not None: raise last_exc
        if job.cancelled: raise KeyboardInterrupt()
        template = (job.meta or {}).get('template','clean')
        if template != 'clean':
            path, derived_fmt = await asyncio.to_thread(ffmpeg_transform, path, template)
            job.fmt = derived_fmt if derived_fmt in {'mp3','m4a','jpg'} else job.fmt
            job.audio = template == 'audio'
        size=path.stat().st_size/1024/1024
        u=await get_user(uid); limit=PREMIUM_MAX_MB if await is_premium(uid) else MAX_MB
        if size>limit: raise RuntimeError(f'Файл {size:.1f} MB превышает лимит {limit} MB')
        await message.edit_text('📤 Отправляю файл…')
        caption=f'🌙 <b>Ravenkai 7.2</b>\n{esc(info.get("title",path.name)[:180])}\n🌐 {platform(job.url)} · {job.quality} · {job.fmt.upper()}\n💾 {size:.1f} MB'
        if (job.meta or {}).get('template') == 'thumbnail':
            await bot.send_photo(job.chat_id,FSInputFile(path),caption=caption)
        elif job.audio: await bot.send_audio(job.chat_id,FSInputFile(path),caption=caption)
        elif path.suffix.lower()=='.mp4': await bot.send_video(job.chat_id,FSInputFile(path),caption=caption,supports_streaming=True)
        else: await bot.send_document(job.chat_id,FSInputFile(path),caption=caption)
        await record_download(uid,job.url,platform(job.url),info.get('title',''),info.get('duration') or 0,job.quality,job.fmt,size,'done')
        await save_bookmark(uid, job.url, info.get('title',''))
        metrics.completed += 1; metrics.bytes_sent += int(size*1024*1024)
        status='done'; await message.edit_text(
            '✅ <b>Готово!</b>',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🔁 Повторить', callback_data=f'retryid:{(await latest_download(uid))["id"]}')],
                [InlineKeyboardButton(text='🔗 Источник', url=job.url)],
            ])
        ); await log_action(uid,'download_done',f'{platform(job.url)} {size:.1f}MB')
    except KeyboardInterrupt:
        if message:
            try: await message.edit_text('🛑 Загрузка отменена.')
            except Exception: pass
        metrics.cancelled += 1
        await record_download(uid,job.url,platform(job.url),info.get('title',''),info.get('duration') or 0,job.quality,job.fmt,size,'cancelled')
    except Exception as e:
        if message:
            try: await message.edit_text(f'❌ <b>Ошибка</b>\n<code>{esc(e)}</code>', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔁 Повторить',callback_data=f'retry:{job.id}')]]))
            except Exception: pass
        metrics.failed += 1
        await record_download(uid,job.url,platform(job.url),info.get('title',''),info.get('duration') or 0,job.quality,job.fmt,size,status,str(e)); await log_action(uid,'download_error',str(e))
    finally:
        shutil.rmtree(folder,ignore_errors=True)


async def run_scheduled(job: ScheduledJob):
    if not await claim_due_schedule(job.id):
        return
    if not await allowed_user(job.user_id):
        return
    jid=uuid.uuid4().hex[:10]
    meta={'title':job.title,'template':job.template,'scheduled_id':job.id,'created':time.monotonic()}
    q=job.quality or '720'; prem=await is_premium(job.user_id)
    task=Job(user_id=job.user_id,chat_id=job.chat_id,url=job.url,quality=q,fmt=job.fmt or 'mp4',audio=job.fmt in {'mp3','m4a','audio'},id=jid,priority=0 if prem else 10,meta=meta)
    try:
        await queue.put(task)
        await bot.send_message(job.chat_id,f'⏰ <b>Плановая задача #{job.id} запущена</b>\nПозиция: {queue.position(jid) or 1}')
    except Exception as exc:
        await bot.send_message(job.chat_id,f'❌ Плановая задача #{job.id} не запустилась: <code>{esc(exc)}</code>')

async def on_startup():
    global cleanup_task
    await init_db(); await init_next_schema(); await init_feature_store(); await queue.start(process_job); await scheduler.start(run_scheduled, load_scheduled_jobs)
    cleanup_task = asyncio.create_task(cleanup_loop(DOWNLOAD_ROOT, int(os.getenv('DOWNLOAD_RETENTION_HOURS','24')), int(os.getenv('CLEANUP_INTERVAL','1800'))), name='ravenkai-cleanup')
    await bot.set_my_commands([BotCommand(command=x,description=d) for x,d in [
        ('start','Главное меню'),('schedule','Запланировать загрузку'),('schedules','Мои планы'),('schedule_cancel','Отменить план'),('help','Помощь'),('history','История'),('profile','Профиль'),('settings','Настройки'),('premium','Premium'),('queue','Очередь'),('cancel','Отменить загрузки'),('health','Состояние бота'),('id','Мой ID'),('bookmarks','Мои закладки'),('save','Сохранить ссылку'),('again','Повторить последнюю'),('mystats','Моя статистика'),('top','Мои платформы'),('export','Экспорт истории'),('jsonexport','JSON экспорт'),('info','Детали записи'),('forget','Удалить запись'),('bookmark','Добавить запись в закладки'),('clearbookmarks','Очистить закладки'),('search','Поиск по истории'),('repeat','Повторить по ID'),('failed','Ошибки'),('duplicates','Дубликаты'),('last','Последняя загрузка'),('cancelall','Отменить всё'),('failedretry','Повторить ошибки'),('privacy','О хранении данных'),('montage','Шаблоны монтажа'),('batch','Пакетная загрузка'),('trial','Пробный период'),('admin','Админ-панель'),('revenue','Доход Stars'),('user','Пользователь'),('preset','Мои пресеты'),('ref','Рефералы'),('refclaim','Активировать рефкод'),('watermark','Watermark'),('autodelete','Автоочистка'),('notifications','Уведомления'),('limits','Лимиты'),('audit','Audit'),('dbbackup','Backup'),('support','Поддержка'),('tickets','Тикеты'),('diag','Диагностика'),('featurelist','Фичи')]])


async def main():
    await on_startup(); log.info('Ravenkai DOWNLOADER Ultra v7.2 started')
    try: await dp.start_polling(bot)
    finally:
        await scheduler.stop()
        await queue.stop()
        if cleanup_task:
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)
        await bot.session.close()

if __name__=='__main__': asyncio.run(main())
