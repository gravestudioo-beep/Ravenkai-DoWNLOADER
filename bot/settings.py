
from .database import get_user, set_user_field

QUALITY_OPTIONS = ['360','480','720','1080','1440','2160']
FORMAT_OPTIONS = ['mp4','webm']
AUDIO_FORMATS = ['mp3','m4a']

async def set_setting(user_id: int, key: str, value):
    allowed={'quality','format','auto_delete','notifications'}
    if key not in allowed: raise ValueError('invalid setting')
    await set_user_field(user_id,key,value)

async def settings(user_id: int):
    row = await get_user(user_id)
    return dict(row) if row else {}
