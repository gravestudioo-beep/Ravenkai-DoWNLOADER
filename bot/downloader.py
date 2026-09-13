
from __future__ import annotations
import asyncio, shutil
from pathlib import Path
from typing import Callable, Optional
from yt_dlp import YoutubeDL
from .utils import human_duration

class DownloadError(Exception):
    pass

def format_selector(quality: str, audio: bool=False) -> str:
    if audio:
        return 'bestaudio/best'
    if quality in {'best','2160','1440'}:
        return 'bv*[height<=2160]+ba/b[height<=2160]'
    q=int(quality)
    return f'bv*[height<={q}]+ba/b[height<={q}]'

def extract_info(url: str) -> dict:
    opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'skip_download': True}
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def run_download(url: str, outdir: str | Path, quality='720', audio=False, fmt='mp4', hook: Optional[Callable]=None, cancel_check: Optional[Callable[[], bool]]=None):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(outdir / '%(title).90s [%(id)s].%(ext)s')
    opts = {
        'outtmpl': outtmpl,
        'format': format_selector(quality, audio),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'merge_output_format': 'mp4' if not audio else None,
        'progress_hooks': [hook] if hook else [],
        'postprocessor_hooks': [],
    }
    if opts['merge_output_format'] is None:
        opts.pop('merge_output_format')
    if audio:
        opts['postprocessors'] = [{'key':'FFmpegExtractAudio','preferredcodec':fmt if fmt in {'mp3','m4a'} else 'mp3'}]
    elif fmt == 'webm':
        opts['merge_output_format'] = 'webm'
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if cancel_check and cancel_check():
        raise KeyboardInterrupt()
    files = [p for p in outdir.iterdir() if p.is_file() and p.suffix.lower() in {'.mp4','.mkv','.webm','.m4a','.mp3','.mov','.m4v'}]
    if not files:
        raise DownloadError('Файл не найден после скачивания')
    return max(files, key=lambda p:p.stat().st_mtime), info

async def download(*args, **kwargs):
    return await asyncio.to_thread(run_download, *args, **kwargs)
