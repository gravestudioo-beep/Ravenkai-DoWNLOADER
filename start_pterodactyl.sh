#!/bin/sh
set -eu

echo '[Angels Downloader] Pterodactyl startup'
: "${BOT_TOKEN:?BOT_TOKEN is not set in Pterodactyl Startup variables}"
: "${ADMIN_IDS:?ADMIN_IDS is not set in Pterodactyl Startup variables}"

mkdir -p data downloads outputs logs
python -m compileall -q bot
exec python bot.py
