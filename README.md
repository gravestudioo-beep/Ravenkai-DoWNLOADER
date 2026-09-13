# 🌙 Ravenkai DOWNLOADER Ultra 5.0

Ravenkai 5.0 is a larger architecture update built around a priority worker queue, safer URL handling, live progress, stronger Premium logic and admin operations.

## 5.0 highlights
- Priority queue: Premium first, regular tasks second.
- Per-user queue limits and duplicate-link protection.
- Live progress message with cancel button.
- Premium expiry is checked by timestamp.
- HTTP/HTTPS URL validation rejects malformed and local/private targets.
- Maintenance mode and queue pause controls.
- `/health` runtime status command.
- Ban automatically marks a user's queued jobs for cancellation.
- SQLite WAL storage, history, profile, settings and audit logs remain supported.
- MP4/WEBM + MP3/M4A, 360p through 4K where allowed.
- Docker + FFmpeg support.

## Environment
Copy `.env.example` to `.env` and set:
- `BOT_TOKEN`
- `ADMIN_IDS`
- `CONCURRENCY` — worker count
- `PER_USER_QUEUE` — max queued/active jobs per user
- `RATE_LIMIT_SECONDS` — minimal delay between link submissions
- `MAX_FILE_MB`
- `PREMIUM_MAX_FILE_MB`
- `DOWNLOAD_DIR`

## Start
```bash
pip install -r requirements.txt
python -m bot.main
```

## Docker
```bash
docker compose up -d --build
```

Use only content you are authorized to download. The project does not implement DRM bypass, account-login scraping, or watermark removal.

## 5.3 additions
- 🔖 Bookmarks: `/save <url>`, `/bookmarks`, automatic save after successful downloads.
- 🧠 Metadata cache to reduce repeated extractor requests.
- 🛡 SSRF-style URL checks against local/private/link-local targets before extraction.
- 📊 Runtime metrics screen and counters for completed/failed/cancelled jobs and sent bytes.
- 🧹 Background cleanup of stale temporary files/cache.
- 🗃️ SQLite indexes and bookmarks table for faster history access.
