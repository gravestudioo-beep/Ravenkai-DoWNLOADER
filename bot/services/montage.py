from __future__ import annotations
import subprocess
from pathlib import Path

TEMPLATES = {
    'clean': ('🎬 Оригинал', 'Без изменений'),
    'mute': ('🔇 Без звука', 'Удалить аудио дорожку'),
    'audio': ('🎵 Только звук', 'Сделать MP3 из видео'),
    'vertical': ('📱 Вертикал 9:16', 'Кадрирование под Shorts/Reels/TikTok'),
    'short30': ('✂️ Первые 30 сек', 'Обрезать ролик до 30 секунд'),
    'clip60': ('✂️ Первые 60 сек', 'Обрезать ролик до 60 секунд'),
    'compress': ('🗜 Сжатие', 'Уменьшить размер через H.264'),
    'square': ('⬛ Квадрат 1:1', 'Кадрирование под квадратный пост'),
    'slow': ('🐌 Slow 0.75×', 'Замедлить ролик и сохранить звук'),
    'thumbnail': ('🖼 Кадр', 'Вырезать превью из первой секунды'),
    'watermark': ('🏷 Ravenkai watermark', 'Наложить лёгкий водяной знак'),
}

def ffmpeg_transform(src: Path, template: str) -> tuple[Path, str]:
    if template not in TEMPLATES or template == 'clean':
        return src, src.suffix.lstrip('.')
    ext = '.jpg' if template == 'thumbnail' else ('.mp3' if template == 'audio' else '.mp4')
    out = src.with_name(src.stem + '_rk_' + template + ext)
    common = ['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(src)]
    if template == 'mute':
        cmd = common + ['-c:v','copy','-an',str(out)]
    elif template == 'audio':
        cmd = common + ['-vn','-c:a','libmp3lame','-q:a','4',str(out)]
    elif template == 'vertical':
        cmd = common + ['-vf','crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac',str(out)]
    elif template == 'short30':
        cmd = common + ['-t','30','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac',str(out)]
    elif template == 'clip60':
        cmd = common + ['-t','60','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac',str(out)]
    elif template == 'compress':
        cmd = common + ['-c:v','libx264','-preset','veryfast','-crf','28','-c:a','aac','-b:a','128k',str(out)]
    elif template == 'square':
        cmd = common + ['-vf',r'crop=min(iw\,ih):min(iw\,ih):(iw-min(iw\,ih))/2:(ih-min(iw\,ih))/2,scale=1080:1080','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac',str(out)]
    elif template == 'slow':
        cmd = common + ['-filter_complex','[0:v]setpts=PTS/0.75[v];[0:a]atempo=0.75[a]','-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac',str(out)]
    elif template == 'thumbnail':
        cmd = common + ['-ss','00:00:01','-frames:v','1','-q:v','2',str(out)]
    elif template == 'watermark':
        cmd = common + ['-vf',"drawtext=text='Ravenkai':fontcolor=white@0.62:fontsize=28:x=w-tw-24:y=h-th-24:box=1:boxcolor=black@0.18:boxborderw=10",'-c:v','libx264','-preset','veryfast','-crf','24','-c:a','copy',str(out)]
    else:
        return src, src.suffix.lstrip('.')
    subprocess.run(cmd, check=True, timeout=900)
    return out, out.suffix.lstrip('.')
