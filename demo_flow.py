"""Показує, що саме бот відповість на конкретний підпис. Нічого не змінює.

    venv\\Scripts\\python.exe demo_flow.py "завтра фіскалізувати"
    venv\\Scripts\\python.exe demo_flow.py "завтра фіскалізувати" --скрін
"""
import sys
from datetime import datetime

import bot as b

args = [a for a in sys.argv[1:] if not a.startswith("--")]
media = any(a.startswith("--") for a in sys.argv[1:])
caption = args[0] if args else "завтра фіскалізувати"

when, note = b.parse_when(caption)
guessed = when is None
if guessed:
    when = b.iso(b.next_nine())

print(f"текст: {caption!r}" + ("  + скріншот" if media else "  (без вкладень)"))
print(f"  час  : {b.human(when)}"
      f"{'   <- часу не було, поставив на 9 ранку' if guessed else ''}")
print(f"  опис : {note!r}\n")

print("1) ОДРАЗУ у відповідь:\n   " + b.confirm(when, 7) + "\n")

row = {"id": 7, "note": note, "remind_at": when, "created_at": b.iso(datetime.now(b.TZ)),
       "creator_name": "Serhii", "creator_id": 547696309,
       "src_msg_id": 1 if media else None, "src_chat_id": 1, "times_sent": 0}

kind = "ОДНЕ повідомлення: скрін + підпис + кнопка" if media else "текстове повідомлення"
print(f"2) У ЧАС X — {kind}:\n")

now = datetime.fromisoformat(when)
for i in range(4):
    row["remind_at"] = b.iso(now)
    row["times_sent"] = i
    if media:
        print("   ┌─────────────────┐")
        print("   │   [ скріншот ]  │")
        print("   └─────────────────┘")
    for line in b.reminder_text(row).split("\n"):
        print("   " + line)
    print("   [ ✅ Готово ]\n")
    now = b.next_occurrence(b.iso(now), now)

print("3) Після натискання — в обох чатах:\n")
n = b.note_of(row)
print(f"   ✅ <s>{n or 'Нагадування'}</s>")
print(f"   закрито · {b.person(388521288, 'Arina')} · {datetime.now(b.TZ):%H:%M}")
print(f"\n4) Кому: {b.targets(row['creator_id'])}  (NOTIFY_ALL={b.NOTIFY_ALL})")
