from __future__ import annotations
from dataclasses import dataclass

PLANS = {
    'trial': {'days': 3, 'stars': 0, 'title': 'Тестовый Premium'},
    'week': {'days': 7, 'stars': 75, 'title': 'Premium 7 дней'},
    'month': {'days': 30, 'stars': 199, 'title': 'Premium 30 дней'},
    'quarter': {'days': 90, 'stars': 499, 'title': 'Premium 90 дней'},
}

def payload(plan: str, user_id: int) -> str:
    return f'rk:{plan}:{user_id}'

def parse_payload(value: str):
    parts = (value or '').split(':')
    if len(parts) != 3 or parts[0] != 'rk' or parts[1] not in PLANS:
        return None, None
    try: return parts[1], int(parts[2])
    except ValueError: return None, None
