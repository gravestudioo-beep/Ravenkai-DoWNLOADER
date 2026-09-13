from __future__ import annotations
from .storage import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    quality TEXT DEFAULT '720',
    format TEXT DEFAULT 'mp4',
    template TEXT DEFAULT 'clean',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_user_presets_user ON user_presets(user_id);
"""

async def init_feature_store():
    async with connect() as db:
        await db.executescript(SCHEMA); await db.commit()

async def save_preset(user_id:int,name:str,quality:str,fmt:str,template:str):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO user_presets(user_id,name,quality,format,template) VALUES(?,?,?,?,?)",(user_id,name[:32],quality,fmt,template)); await db.commit()

async def list_presets(user_id:int):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM user_presets WHERE user_id=? ORDER BY name",(user_id,))).fetchall()

async def get_preset(user_id:int,name:str):
    async with connect() as db:
        return await (await db.execute("SELECT * FROM user_presets WHERE user_id=? AND name=?",(user_id,name))).fetchone()

async def delete_preset(user_id:int,name:str):
    async with connect() as db:
        cur=await db.execute("DELETE FROM user_presets WHERE user_id=? AND name=?",(user_id,name)); await db.commit(); return cur.rowcount>0

async def ensure_referral(user_id:int):
    async with connect() as db:
        await db.executescript("""CREATE TABLE IF NOT EXISTS referrals (user_id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, invited INTEGER DEFAULT 0, reward_days INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS referral_uses (id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER NOT NULL, invited_id INTEGER NOT NULL UNIQUE, created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")
        row=await (await db.execute("SELECT code FROM referrals WHERE user_id=?",(user_id,))).fetchone()
        if row: return row['code']
        import secrets
        code='RK'+secrets.token_hex(4).upper()
        await db.execute("INSERT INTO referrals(user_id,code) VALUES(?,?)",(user_id,code)); await db.commit(); return code

async def claim_referral(invited_id:int, code:str):
    async with connect() as db:
        row=await (await db.execute("SELECT user_id FROM referrals WHERE code=?",(code.strip().upper(),))).fetchone()
        if not row or int(row['user_id'])==int(invited_id): return False, 'invalid'
        try:
            await db.execute("INSERT INTO referral_uses(referrer_id,invited_id) VALUES(?,?)",(row['user_id'],invited_id))
        except Exception: return False, 'used'
        await db.execute("UPDATE referrals SET invited=invited+1, reward_days=reward_days+1 WHERE user_id=?",(row['user_id'],)); await db.commit()
        return True, int(row['user_id'])

async def referral_stats(user_id:int):
    async with connect() as db:
        row=await (await db.execute("SELECT code,invited,reward_days FROM referrals WHERE user_id=?",(user_id,))).fetchone()
        return row

async def create_ticket(user_id:int, text:str):
    async with connect() as db:
        await db.execute("CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,text TEXT NOT NULL,status TEXT DEFAULT 'open',created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        cur=await db.execute("INSERT INTO tickets(user_id,text) VALUES(?,?)",(user_id,text[:2000])); await db.commit(); return cur.lastrowid

async def list_tickets(limit:int=30):
    async with connect() as db:
        await db.execute("CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,text TEXT NOT NULL,status TEXT DEFAULT 'open',created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        return await (await db.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT ?",(limit,))).fetchall()

async def close_ticket(ticket_id:int):
    async with connect() as db:
        cur=await db.execute("UPDATE tickets SET status='closed' WHERE id=?",(ticket_id,)); await db.commit(); return cur.rowcount>0
