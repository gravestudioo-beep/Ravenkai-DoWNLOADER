from pathlib import Path
import shutil,subprocess

def snapshot(db_path:Path):
    _,_,free=shutil.disk_usage(db_path.parent)
    db_mb=db_path.stat().st_size/1024/1024 if db_path.exists() else 0
    try:
        p=subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,timeout=3); ff=p.stdout.splitlines()[0] if p.stdout else 'unknown'
    except Exception: ff='unavailable'
    return {'disk_free_gb':free/1024/1024/1024,'db_mb':db_mb,'ffmpeg':ff}
