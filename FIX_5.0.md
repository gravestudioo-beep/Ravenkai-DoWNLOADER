# Ravenkai DOWNLOADER Ultra 5.0

## Major upgrade
- Priority queue: Premium jobs are processed before regular jobs.
- Per-user queue cap with duplicate URL protection.
- Live progress with cancellable job buttons.
- Premium expiration is now respected instead of relying only on a boolean flag.
- Stronger public-URL validation with localhost/private-network rejection.
- Maintenance mode + queue pause controls for admins.
- `/health` command for a quick runtime snapshot.
- Cleaner profile and queue screens.
- Admin ban now also cancels the user's queued jobs.
- Safer temporary directory lifecycle.
- New environment controls: `PER_USER_QUEUE`, `RATE_LIMIT_SECONDS`.
