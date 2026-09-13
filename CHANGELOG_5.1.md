# Ravenkai DOWNLOADER Ultra 5.1 — feature expansion

Added new modules instead of keeping all logic in one file:
- `bot/security.py` — stronger public URL/IP validation.
- `bot/cache.py` — TTL metadata cache.
- `bot/cleanup.py` — automatic retention cleanup.
- `bot/metrics.py` — in-process runtime counters.
- `bot/bookmarks.py` — bookmark service layer.

Database additions:
- `bookmarks` table.
- History/bookmark indexes.

User features:
- Bookmarks menu and `/bookmarks`.
- `/save <url>` shortcut.
- Automatic bookmark on successful download.
- Metrics screen.

Operational features:
- Background cleanup loop.
- Cached extractor metadata.
- Extra URL target validation.
