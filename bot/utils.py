from __future__ import annotations
import html, ipaddress, re
from urllib.parse import urlparse

DOMAINS = {
    'youtube.com':'YouTube','youtu.be':'YouTube','tiktok.com':'TikTok','instagram.com':'Instagram',
    'vk.com':'VK','twitter.com':'X','x.com':'X','reddit.com':'Reddit','vimeo.com':'Vimeo',
    'twitch.tv':'Twitch','soundcloud.com':'SoundCloud','facebook.com':'Facebook','fb.watch':'Facebook',
    'pinterest.com':'Pinterest','dailymotion.com':'Dailymotion','streamable.com':'Streamable'
}
URL_RE = re.compile(r'^https?://[^\s]+$', re.I)


def platform(url: str) -> str:
    host = urlparse(url).netloc.lower().split('@')[-1].split(':')[0].removeprefix('www.')
    for domain, name in DOMAINS.items():
        if host == domain or host.endswith('.' + domain):
            return name
    return host or 'Unknown'


def valid_url(url: str) -> bool:
    value = (url or '').strip()
    if len(value) > 4096 or not URL_RE.match(value):
        return False
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip('.')
        if host in {'localhost'} or host.endswith('.local'):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


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
