
from __future__ import annotations
import html, re
from urllib.parse import urlparse

DOMAINS = {
    'youtube.com':'YouTube','youtu.be':'YouTube','tiktok.com':'TikTok','instagram.com':'Instagram',
    'vk.com':'VK','twitter.com':'X','x.com':'X','reddit.com':'Reddit','vimeo.com':'Vimeo',
    'twitch.tv':'Twitch','soundcloud.com':'SoundCloud','facebook.com':'Facebook','fb.watch':'Facebook',
    'pinterest.com':'Pinterest','dailymotion.com':'Dailymotion','streamable.com':'Streamable'
}
URL_RE = re.compile(r'^https?://[^\s]+$', re.I)

def platform(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix('www.')
    for domain, name in DOMAINS.items():
        if host == domain or host.endswith('.' + domain):
            return name
    return host or 'Unknown'

def valid_url(url: str) -> bool:
    return bool(URL_RE.match((url or '').strip()))

def esc(value) -> str:
    return html.escape(str(value), quote=False)

def bar(percent: float, width: int=18) -> str:
    p = max(0.0, min(100.0, float(percent)))
    filled = int(p * width / 100)
    return '█'*filled + '░'*(width-filled)

def human_bytes(value: float | int) -> str:
    n=float(value or 0)
    for unit in ('B','KB','MB','GB'):
        if n < 1024 or unit == 'GB': return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} GB'

def human_duration(seconds: int | float) -> str:
    s=int(seconds or 0)
    if s <= 0: return '—'
    h,s=divmod(s,3600); m,s=divmod(s,60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

def human_speed(value: float | int | None) -> str:
    return human_bytes(value or 0) + '/s'
