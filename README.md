# Ravenkai DOWNLOADER Ultra 6.2

Telegram downloader with yt-dlp, local SQLite, 3-day Premium trial, Telegram Stars payments, template-based FFmpeg montage, priority queue, batch downloads, automatic transient-error retries, montage templates and admin panel.

## Structure
- `bot/handlers` — user/admin handlers
- `bot/keyboards` — inline keyboards
- `bot/services` — storage, queue, downloader, security, montage, payments
- `assets` — all visual assets
- `data` — runtime SQLite database (`ravenkai.db`)
- `pterodactyl` — startup helpers

## Premium
New users receive a 3-day Premium trial. Paid plans use Telegram Stars (`XTR`). Configure BotFather payments/test environment before production use.

## Montage templates
Mute audio, extract MP3, 9:16 vertical crop, first 30 seconds, compression, square 1:1 and slow 0.75× are available through the `🎬 Монтаж` flow. FFmpeg is required and included in Docker.

## Run
Set `BOT_TOKEN` in `.env`, then run `python -m bot.main`.

## Batch mode
Use `/batch` followed by 2–5 public URLs, one per line. A single quality selection is applied to the whole batch and each URL becomes an independent queue job.

## Admin extras
`/user ID` shows a user profile, while `/revenue` shows Telegram Stars totals.


### 6.2 additions
- Persistent scheduler commands: `/schedule`, `/schedules`, `/schedule_cancel`.
- New montage templates: 60-second clip and thumbnail frame.
- Scheduled jobs are stored in `data/ravenkai.db` and restored after restart.

## Smart presets (6.3)
Users can create reusable download + montage presets with `/preset name [quality] [format] [template]` and manage them from `/preset`.

## Referrals (6.4)
`/ref` creates a referral code; `/refclaim CODE` activates a code once per account.

## Watermark template (6.5)
New montage template `watermark` adds a subtle Ravenkai watermark using FFmpeg.

## Delivery controls (6.6)
`/autodelete on|off` and `/notifications on|off` are persisted per user.

## Limits view (6.7)
`/limits` shows the current queue and file-size limits for the account.

## Admin audit (6.8)
Admins can inspect recent actions with `/audit`.

## Admin backup (6.9)
Admins can export a SQLite snapshot with `/dbbackup` without shipping the live DB inside the release.

## Support tickets (7.0)
Users can open a support ticket with `/support TEXT`; admins review them with `/tickets`.

## Diagnostics (7.1)
`/diag` shows basic runtime, disk, database and FFmpeg diagnostics.

## Feature catalog (7.2)
`/featurelist` lists the current user-facing feature packs. `/refadmin` is an admin entry point for referral tooling.

## 7.2 creator cycle
This release closes the 10-update creator cycle from 6.3 through 7.2 with presets, referrals, montage watermarking, delivery controls, limits, admin audit/backup, support tickets, diagnostics, and a feature catalog.


## 7.3 → 8.2
- Smart bookmark collections
- Filename templates
- Recurring schedules
- Retry visibility and backoff policy
- Admin user controls
- Analytics
- Backup rotation/history
- Health monitor
- Download profiles
- Unified history search
