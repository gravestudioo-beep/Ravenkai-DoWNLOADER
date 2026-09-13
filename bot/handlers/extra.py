from __future__ import annotations
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from ..services.feature_store import save_preset, list_presets, get_preset, delete_preset
from ..services.storage import get_user
from ..services.utils import esc
from ..services.montage import TEMPLATES
from ..services.settings import QUALITY_OPTIONS, FORMAT_OPTIONS

router=Router()

def _admin_ids():
    import os
    return {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}

@router.message(Command('preset'))
async def preset_cmd(m:Message):
    parts=(m.text or '').split()
    if len(parts)==1:
        rows=await list_presets(m.from_user.id)
        if not rows: return await m.answer('🎛 Пресетов пока нет.\nСоздай: /preset name 1080 mp4 vertical')
        kb=[[InlineKeyboardButton(text=f'▶️ {r["name"]}',callback_data=f'preset:use:{r["id"]}'), InlineKeyboardButton(text='🗑',callback_data=f'preset:del:{r["id"]}')] for r in rows]
        return await m.answer('🎛 <b>Мои пресеты</b>\n\n'+ '\n'.join(f'• {esc(r["name"])} — {esc(r["quality"])}p · {esc(r["format"])} · {esc(r["template"])}' for r in rows),reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    if len(parts)<2: return await m.answer('Использование: /preset имя [quality] [format] [template]')
    name=parts[1]; u=await get_user(m.from_user.id); quality=parts[2] if len(parts)>2 else (u['quality'] if u else '720'); fmt=parts[3] if len(parts)>3 else (u['format'] if u else 'mp4'); template=parts[4] if len(parts)>4 else 'clean'
    if quality not in {'360','480','720','1080','1440','2160','best'}: return await m.answer('❌ Качество: 360/480/720/1080/1440/2160/best')
    if fmt not in {'mp4','mp3','m4a'}: return await m.answer('❌ Формат: mp4/mp3/m4a')
    if template not in TEMPLATES: return await m.answer('❌ Неизвестный шаблон монтажа.')
    await save_preset(m.from_user.id,name,quality,fmt,template); await m.answer(f'✅ Пресет <b>{esc(name)}</b> сохранён.')

@router.callback_query(F.data.startswith('preset:del:'))
async def preset_del(c:CallbackQuery):
    rows=await list_presets(c.from_user.id); rid=int(c.data.split(':')[-1]); row=next((r for r in rows if int(r['id'])==rid),None)
    if not row: return await c.answer('Уже удалён.',show_alert=True)
    await delete_preset(c.from_user.id,row['name']); await c.answer('Удалено.')
    await preset_cmd(c.message)

@router.message(Command('ref'))
async def ref_cmd(m:Message):
    from ..services.feature_store import ensure_referral, referral_stats
    code=await ensure_referral(m.from_user.id); row=await referral_stats(m.from_user.id)
    await m.answer(f'🤝 <b>Реферальная программа</b>\n\nКод: <code>{code}</code>\nПриглашено: <b>{int(row["invited"] if row else 0)}</b>\nБонусных дней: <b>{int(row["reward_days"] if row else 0)}</b>\n\nДруг может активировать: <code>/refclaim {code}</code>')

@router.message(Command('refclaim'))
async def refclaim_cmd(m:Message):
    from ..services.feature_store import claim_referral
    parts=(m.text or '').split(maxsplit=1)
    if len(parts)<2: return await m.answer('/refclaim КОД')
    ok,who=await claim_referral(m.from_user.id,parts[1])
    await m.answer('✅ Реферальный код активирован.' if ok else '❌ Код недействителен или уже использован.')

@router.message(Command('watermark'))
async def watermark_cmd(m:Message):
    parts=(m.text or '').split(maxsplit=1)
    if len(parts)==1: return await m.answer('🏷 Шаблон watermark добавляет небольшой знак Ravenkai. Используй `/montage` и выбери его.')
    await m.answer('🏷 Персональный текст пока не используется; включён безопасный шаблон Ravenkai.')

@router.message(Command('autodelete'))
async def autodelete_cmd(m:Message):
    from ..services.storage import set_user_field, get_user
    parts=(m.text or '').split(); mode=parts[1].lower() if len(parts)>1 else ''
    if mode not in {'on','off'}: return await m.answer('/autodelete on|off')
    await set_user_field(m.from_user.id,'auto_delete',1 if mode=='on' else 0); await m.answer(f'🧹 Автоочистка: <b>{mode.upper()}</b>')

@router.message(Command('notifications'))
async def notifications_cmd(m:Message):
    from ..services.storage import set_user_field
    parts=(m.text or '').split(); mode=parts[1].lower() if len(parts)>1 else ''
    if mode not in {'on','off'}: return await m.answer('/notifications on|off')
    await set_user_field(m.from_user.id,'notifications',1 if mode=='on' else 0); await m.answer(f'🔔 Уведомления: <b>{mode.upper()}</b>')

@router.message(Command('limits'))
async def limits_cmd(m:Message):
    from ..services.storage import get_setting
    from ..services.premium import is_premium
    max_queue=await get_setting('max_queue','2'); prem=await is_premium(m.from_user.id)
    max_mb='95 MB' if prem else '49 MB'
    await m.answer(f'📏 <b>Лимиты</b>\n\nОчередь: <b>{esc(max_queue)}</b>\nРазмер файла: <b>{max_mb}</b>\nPremium: {"⭐ да" if prem else "нет"}')

@router.message(Command('audit'))
async def audit_cmd(m:Message):
    import os
    if m.from_user.id not in {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}: return await m.answer('⛔ Нет доступа.')
    from ..services.storage import admin_logs
    rows=await admin_logs(30)
    if not rows: return await m.answer('🧾 Логи пусты.')
    text='🧾 <b>Audit log</b>\n\n'+'\n'.join(f'#{r["id"]} · {r["action"]} · {str(r["details"] or "")[:100]}' for r in rows)
    await m.answer(text)

@router.message(Command('dbbackup'))
async def dbbackup_cmd(m:Message):
    import os, sqlite3, tempfile
    from pathlib import Path
    if m.from_user.id not in {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}: return await m.answer('⛔ Нет доступа.')
    from ..services.storage import DB_PATH
    tmp=Path(tempfile.mkstemp(prefix='ravenkai-backup-',suffix='.db')[1])
    try:
        src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(tmp); src.backup(dst); dst.close(); src.close()
        from aiogram.types import FSInputFile
        await m.answer_document(FSInputFile(tmp),caption='🗄 SQLite backup')
    finally: tmp.unlink(missing_ok=True)

@router.message(Command('support'))
async def support_cmd(m:Message):
    from ..services.feature_store import create_ticket
    parts=(m.text or '').split(maxsplit=1)
    if len(parts)<2: return await m.answer('🆘 Использование: /support текст проблемы')
    tid=await create_ticket(m.from_user.id,parts[1]); await m.answer(f'🆘 Тикет <b>#{tid}</b> создан. Администратор увидит его в /tickets.')

@router.message(Command('tickets'))
async def tickets_cmd(m:Message):
    import os
    if m.from_user.id not in {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}: return await m.answer('⛔ Нет доступа.')
    from ..services.feature_store import list_tickets
    rows=await list_tickets(30)
    if not rows: return await m.answer('🆘 Тикетов нет.')
    await m.answer('🆘 <b>Тикеты</b>\n\n'+'\n\n'.join(f'#{r["id"]} · user <code>{r["user_id"]}</code> · {r["status"]}\n{esc(r["text"][:300])}' for r in rows))

@router.message(Command('diag'))
async def diag_cmd(m:Message):
    import os, shutil, subprocess, platform as pf
    from ..services.storage import DB_PATH
    total,used,free=shutil.disk_usage(DB_PATH.parent)
    db_mb=DB_PATH.stat().st_size/1024/1024 if DB_PATH.exists() else 0
    try:
        ff=subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,timeout=3)
        ffv=(ff.stdout.splitlines()[0] if ff.stdout else 'unknown')[:100]
    except Exception: ffv='unavailable'
    await m.answer(f'🩺 <b>Diagnostics</b>\n\nOS: {esc(pf.system())}\nPython: {esc(pf.python_version())}\nDisk free: {free/1024/1024/1024:.1f} GB\nDB: {db_mb:.2f} MB\nFFmpeg: <code>{esc(ffv)}</code>')

@router.message(Command('featurelist'))
async def featurelist_cmd(m:Message):
    await m.answer('✨ <b>Ravenkai feature catalog</b>\n\n🎛 Presets\n🤝 Referrals\n🏷 Watermark montage\n🧹 Delivery controls\n📏 Limits\n🧾 Admin audit\n🗄 DB backup (admin)\n🆘 Support tickets\n🩺 Diagnostics')

@router.message(Command('refadmin'))
async def refadmin_cmd(m:Message):
    import os
    if m.from_user.id not in {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}: return await m.answer('⛔ Нет доступа.')
    from ..services.feature_store import list_tickets
    await m.answer('🤝 Реферальная аналитика доступна по /ref у пользователя; расширенные агрегаты оставлены без изменения схемы downloads/payments.')
