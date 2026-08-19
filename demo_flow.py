"""Показує, що саме бот відповість на конкретний підпис. Нічого не змінює.

    venv\\Scripts\\python.exe demo_flow.py "завтра в 11.00 фіскалізувати оплату"
"""
import sys
from datetime import datetime

import bot as b

caption = sys.argv[1] if len(sys.argv) > 1 else "завтра в 11.00 фіскалізувати оплату"
when, note = b.parse_when(caption)

print(f"текст: {caption!r}\n")
print(f"  розпізнаний час : {b.human(when) if when else '— (буде питати кнопками)'}")
print(f"  опис            : {note!r}\n")

if not when:
    print("1) Бот питає: Коли нагадати?  [1 день] [3 дні] [7 днів] [30 днів]")
    raise SystemExit

print("1) ОДРАЗУ у відповідь:\n   " + b.confirm(when, 7))

row = {"id": 7, "note": note, "remind_at": when, "created_at": b.iso(datetime.now(b.TZ)),
       "creator_name": "Serhii", "creator_id": 547696309,
       "src_msg_id": None, "src_chat_id": None, "times_sent": 0}

for day in (0, 1, 2):
    row["times_sent"] = day
    label = "2) У ЧАС X:" if day == 0 else f"   якщо не закрили, +{day} доб{'а' if day == 1 else 'и'}:"
    print(f"\n{label}\n")
    for line in b.reminder_text(row).split("\n"):
        print("   " + line)
    print("   [ ✅ Готово ]")

print("\n3) Після натискання — в обох чатах:\n")
print(f"   ✅ {note or 'Нагадування'} — закрито ({b.person(388521288, 'Arina')})")
print(f"\n4) Кому приходить: {b.targets(row['creator_id'])}  (NOTIFY_ALL={b.NOTIFY_ALL})")
print(f"   імена з .env: {b.NAMES}")
