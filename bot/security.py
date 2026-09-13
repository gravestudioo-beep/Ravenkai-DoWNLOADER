from __future__ import annotations
from urllib.parse import urlparse
import ipaddress
import socket

ALLOWED_SCHEMES = {'http','https'}
BLOCKED_HOSTS = {'localhost','localhost.localdomain','0.0.0.0','127.0.0.1','::1'}


def validate_public_url(value: str) -> tuple[bool, str]:
    try:
        p = urlparse(value.strip())
    except Exception:
        return False, 'Некорректный URL.'
    if p.scheme.lower() not in ALLOWED_SCHEMES or not p.netloc:
        return False, 'Нужна публичная http/https-ссылка.'
    host = (p.hostname or '').lower().rstrip('.')
    if not host or host in BLOCKED_HOSTS:
        return False, 'Локальные адреса запрещены.'
    try:
        infos = socket.getaddrinfo(host, None)
        for item in infos:
            addr = ipaddress.ip_address(item[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
                return False, 'Ссылка ведёт на локальный или служебный адрес.'
    except socket.gaierror:
        pass
    return True, ''
