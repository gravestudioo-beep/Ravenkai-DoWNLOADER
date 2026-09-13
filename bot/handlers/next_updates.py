from __future__ import annotations
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from ..services.storage import (
    collection_create, collection_list, collection_add_bookmark, collection_items, collection_delete,
    get_user_profile, set_filename_template, set_download_profile,
    create_recurring, list_recurring, delete_recurring,
    list_retries, analytics_for_user, list_backups, register_backup, DB_PATH,
    search_history,
)
from ..services.utils import esc, valid_url
import os, sqlite3, shutil, subprocess, platform as pf, re
from datetime import datetime

router = Router()

def _admins():
    return {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}

@router.message(Command('collection'))
async def collection_cmd(m: Message):
    parts=(m.text or '').split(maxsplit=1)
    if len(parts)<2: return await m.answer('Использование: /collection название')
    await collection_create(m.from_user.id, parts[1])
    await m.answer(f'📚 Коллекция <b>{esc(parts[1])}</b> готова.')

@router.message(Command('collections'))
async def collections_cmd(m: Message):
    rows=await collection_list(m.from_user.id)
    if not rows: return await m.answer('📚 Коллекций пока нет. Создай: /collection имя')
    await m.answer('📚 <b>Коллекции</b>\n\n'+'\n'.join(f'• {esc(r["name"])}' for r in rows))

@router.message(Command('collection_add'))
async def collection_add_cmd(m: Message):
    p=(m.text or '').split()
    if len(p)<3 or not p[2].isdigit(): return await m.answer('/collection_add ИМЯ BOOKMARK_ID')
    ok=await collection_add_bookmark(m.from_user.id,p[1],int(p[2]))
    await m.answer('✅ Добавлено в коллекцию.' if ok else '❌ Коллекция или закладка не найдены.')

@router.message(Command('collection_show'))
async def collection_show_cmd(m: Message):
    p=(m.text or '').split(maxsplit=1)
    if len(p)<2: return await m.answer('/collection_show ИМЯ')
    rows=await collection_items(m.from_user.id,p[1])
    if not rows: return await m.answer('📚 Коллекция пуста.')
    await m.answer('📚 <b>'+esc(p[1])+'</b>\n\n'+'\n'.join(f'#{r["id"]} · {esc((r["title"] or r["url"])[:80])}' for r in rows))

@router.message(Command('collection_del'))
async def collection_del_cmd(m: Message):
    p=(m.text or '').split(maxsplit=1)
    if len(p)<2: return await m.answer('/collection_del ИМЯ')
    await m.answer('🗑 Коллекция удалена.' if await collection_delete(m.from_user.id,p[1]) else '❌ Не найдено.')

@router.message(Command('filename'))
async def filename_cmd(m: Message):
    p=(m.text or '').split(maxsplit=1)
    if len(p)==1:
        prof=await get_user_profile(m.from_user.id)
        return await m.answer('📝 Текущий шаблон: <code>'+esc(prof['filename_template'])+'</code>\nТокены: {title} {id} {date} {platform}')
    tpl=p[1].strip()
    if len(tpl)>120 or not any(t in tpl for t in ('{title}','{id}','{date}','{platform}')):
        return await m.answer('❌ Добавь один из токенов: {title}, {id}, {date}, {platform}.')
    await set_filename_template(m.from_user.id,tpl)
    await m.answer('✅ Шаблон имени сохранён.')

@router.message(Command('download_profile'))
async def dl_profile_cmd(m: Message):
    p=(m.text or '').split()
    profile=p[1].lower() if len(p)>1 else ''
    if profile not in {'fast','balanced','max'}:
        prof=await get_user_profile(m.from_user.id)
        return await m.answer(f'⚙️ Профиль: <b>{esc(prof["download_profile"])}</b>\nДоступно: fast / balanced / max')
    await set_download_profile(m.from_user.id,profile)
    await m.answer(f'✅ Профиль скачивания: <b>{profile}</b>')

@router.message(Command('recurring'))
async def recurring_cmd(m: Message):
    p=(m.text or '').split(maxsplit=4)
    if len(p)==1:
        rows=await list_recurring(m.from_user.id)
        if not rows: return await m.answer('⏰ Повторяющихся задач нет.')
        return await m.answer('⏰ <b>Recurring</b>\n\n'+'\n'.join(f'#{r["id"]} · {r["cadence"]} {int(r["hour"]):02d}:{int(r["minute"]):02d} · {esc(r["url"][:65])}' for r in rows))
    if p[1].lower()=='cancel' and len(p)>2 and p[2].isdigit():
        return await m.answer('🗑 Удалено.' if await delete_recurring(m.from_user.id,int(p[2])) else '❌ Не найдено.')
    if len(p)<4: return await m.answer('/recurring daily|weekly HH:MM URL [quality]')
    cadence,hm,url=p[1].lower(),p[2],p[3]
    quality=p[4] if len(p)>4 else '720'
    if cadence not in {'daily','weekly'} or not re.fullmatch(r'\d{1,2}:\d{2}',hm): return await m.answer('❌ cadence: daily/weekly и время HH:MM')
    ok,reason=valid_url(url)
    if not ok: return await m.answer('❌ '+esc(reason))
    h,mi=map(int,hm.split(':'))
    rid=await create_recurring(m.from_user.id,m.chat.id,url,cadence,h,mi,0,quality,'mp4','clean')
    await m.answer(f'✅ Повторяющаяся задача <b>#{rid}</b> создана.')

@router.message(Command('retries'))
async def retries_cmd(m: Message):
    rows=await list_retries(m.from_user.id,20)
    if not rows: return await m.answer('🔁 Отложенных retry нет.')
    await m.answer('🔁 <b>Retry</b>\n\n'+'\n'.join(f'#{r["id"]} · {r["attempts"]} попыток · {esc(r["status"])} · {esc(r["url"][:60])}' for r in rows))

@router.message(Command('analytics'))
async def analytics_cmd(m: Message):
    a=await analytics_for_user(m.from_user.id)
    top='\n'.join(f'• {esc(str(p or "unknown"))}: {n}' for p,n in a['top']) or '—'
    await m.answer(f'📊 <b>Твоя аналитика</b>\n\nВсего задач: <b>{a["total"]}</b>\nУспешно: <b>{a["done"]}</b>\nОбъём: <b>{a["mb"]:.1f} MB</b>\n\n<b>Топ платформ</b>\n{top}')

@router.message(Command('backups'))
async def backups_cmd(m: Message):
    if m.from_user.id not in _admins(): return await m.answer('⛔ Нет доступа.')
    rows=await list_backups(10)
    if not rows: return await m.answer('🗄 Backup history пуста.')
    await m.answer('🗄 <b>Backups</b>\n\n'+'\n'.join(f'#{r["id"]} · {r["size_mb"]:.1f} MB · {esc(r["created_at"])}' for r in rows))

@router.message(Command('backup_now'))
async def backup_now_cmd(m: Message):
    if m.from_user.id not in _admins(): return await m.answer('⛔ Нет доступа.')
    stamp=datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out=DB_PATH.parent/f'ravenkai_backup_{stamp}.db'
    src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(out); src.backup(dst); dst.close(); src.close()
    mb=out.stat().st_size/1024/1024
    await register_backup(str(out),mb)
    from aiogram.types import FSInputFile
    await m.answer_document(FSInputFile(out),caption=f'🗄 Backup {mb:.1f} MB')

@router.message(Command('health2'))
async def health2_cmd(m: Message):
    _,_,free=shutil.disk_usage(DB_PATH.parent)
    dbmb=DB_PATH.stat().st_size/1024/1024 if DB_PATH.exists() else 0
    try:
        ff=subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,timeout=3); fv=ff.stdout.splitlines()[0] if ff.stdout else 'unknown'
    except Exception: fv='unavailable'
    await m.answer(f'🩺 <b>Health Monitor</b>\n\nPlatform: <code>{esc(pf.system())}</code>\nDisk free: <b>{free/1024/1024/1024:.1f} GB</b>\nDB: <b>{dbmb:.2f} MB</b>\nFFmpeg: <code>{esc(fv[:90])}</code>')

@router.message(Command('find'))
async def find_cmd(m: Message):
    p=(m.text or '').split(maxsplit=1)
    if len(p)<2: return await m.answer('/find запрос')
    rows=await search_history(m.from_user.id,p[1],20)
    if not rows: return await m.answer('🔎 Ничего не найдено.')
    await m.answer('🔎 <b>Поиск</b>\n\n'+'\n'.join(f'#{r["id"]} · {esc((r["title"] or r["url"])[:90])} · {r["status"]}' for r in rows))

@router.message(Command('userban'))
async def userban_cmd(m: Message):
    if m.from_user.id not in _admins(): return await m.answer('⛔ Нет доступа.')
    p=(m.text or '').split()
    if len(p)<2 or not p[1].isdigit(): return await m.answer('/userban ID')
    from ..services.storage import set_user_field
    await set_user_field(int(p[1]),'banned',1); await m.answer('⛔ Пользователь заблокирован.')

@router.message(Command('userunban'))
async def userunban_cmd(m: Message):
    if m.from_user.id not in _admins(): return await m.answer('⛔ Нет доступа.')
    p=(m.text or '').split()
    if len(p)<2 or not p[1].isdigit(): return await m.answer('/userunban ID')
    from ..services.storage import set_user_field
    await set_user_field(int(p[1]),'banned',0); await m.answer('✅ Пользователь разблокирован.')

@router.message(Command('usergrant'))
async def usergrant_cmd(m: Message):
    if m.from_user.id not in _admins(): return await m.answer('⛔ Нет доступа.')
    p=(m.text or '').split()
    if len(p)<3 or not p[1].isdigit() or not p[2].isdigit(): return await m.answer('/usergrant ID DAYS')
    from ..services.premium import grant_premium
    until=await grant_premium(int(p[1]),int(p[2])); await m.answer(f'⭐ Premium выдан до <b>{esc(until)}</b>.')

@router.message(Command('userreset'))
async def userreset_cmd(m: Message):
    if m.from_user.id not in _admins(): return await m.answer('⛔ Нет доступа.')
    p=(m.text or '').split()
    if len(p)<2 or not p[1].isdigit(): return await m.answer('/userreset ID')
    from ..services.storage import clear_history, clear_bookmarks
    await clear_history(int(p[1])); await clear_bookmarks(int(p[1])); await m.answer('🧹 История и закладки пользователя очищены.')
