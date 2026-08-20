"""Копія бази нагадувань. Тримає 14 останніх, старіші видаляє.

Разова перевірка:
    venv/bin/python deploy/backup.py

Щодня о 3:00 через cron (crontab -e):
    0 3 * * * /повний/шлях/venv/bin/python /повний/шлях/deploy/backup.py
"""
import datetime
import os
import pathlib
import sqlite3

KEEP = 14

root = pathlib.Path(__file__).resolve().parent.parent
src_path = pathlib.Path(os.environ.get("DB_PATH", root / "reminders.db"))
if not src_path.is_absolute():
    src_path = root / src_path

if not src_path.exists():
    raise SystemExit(f"бази немає: {src_path}")

dst_dir = root / "backups"
dst_dir.mkdir(exist_ok=True)
dst = dst_dir / f"reminders-{datetime.date.today().isoformat()}.db"

# .backup() коректно копіює базу навіть коли бот саме в неї пише
src = sqlite3.connect(src_path)
out = sqlite3.connect(dst)
with out:
    src.backup(out)
out.close()
src.close()

copies = sorted(dst_dir.glob("reminders-*.db"), reverse=True)
for old in copies[KEEP:]:
    old.unlink()

print(f"копія: {dst.name}  ({dst.stat().st_size} байт), "
      f"усього копій: {min(len(copies), KEEP)}")
