import sqlite3

def make_backup(db_path,out_path):
    src=sqlite3.connect(db_path); dst=sqlite3.connect(out_path)
    try: src.backup(dst)
    finally: dst.close(); src.close()
    return out_path
