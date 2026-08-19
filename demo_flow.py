"""Показує, що саме бот відповість на конкретний підпис. Нічого не змінює.

    venv\\Scripts\\python.exe demo_flow.py "завтра в 11.00 фіскалізувати оплату"
"""
import sys
from datetime import datetime

import bot as b

caption = sys.argv[1] if len(sys.argv) > 1 else "завтра в 11.00 фіскалізувати оплату"
when, note = b.parse_when(caption)
guessed = when is None
if guessed:
    when = b.iso(b.next_nine())

print(f"текст: {caption!r}\n")
print(f"  розпізнаний час : {b.human(when)}"
      f"{'   <- часу в тексті не було, поставив на 9 ранку' if guessed else ''}")
print(f"  опис            : {note!r}\n")

print("1) ОДРАЗУ у відповідь:\n   " + b.confirm(when, 7))

row = {"id": 7, "note": note, "remind_at": when, "created_at": b.iso(datetime.now(b.TZ)),
       "creator_name": "Serhii", "creator_id": 547696309,
       "src_msg_id": None, "src_chat_id": None, "times_sent": 0}

print("\n2) Показ і повтори, якщо не тиснути «Готово»:\n")
now = datetime.fromisoformat(when)
for i in range(5):
    row["remind_at"] = b.iso(now)
    row["times_sent"] = i
    print(f"   {b.reminder_text(row).splitlines()[0]}")
    print(f"   {b.reminder_text(row).splitlines()[1]}   [ ✅ Готово ]")
    print(f"      {'':<3}v")
    now = b.next_occurrence(b.iso(now), now)

print("\n3) Після натискання — в обох чатах:\n")
print(f"   ✅ {note or 'Нагадування'} — закрито ({b.person(388521288, 'Arina')})")
print(f"\n4) Кому приходить: {b.targets(row['creator_id'])}  (NOTIFY_ALL={b.NOTIFY_ALL})")
print(f"   імена з .env: {b.NAMES}")
