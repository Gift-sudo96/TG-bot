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

AUTHOR = 547696309          # Сергій
when, note = b.parse_when(caption)
guessed = when is None
if guessed:
    when = b.iso(b.next_nine())

row = {"id": 7, "note": note, "remind_at": when, "created_at": b.iso(datetime.now(b.TZ)),
       "creator_name": "Serhii", "creator_id": AUTHOR,
       "src_msg_id": 1 if media else None, "src_chat_id": 1, "times_sent": 0}
who_ids = b.targets(AUTHOR)
who = ", ".join(b.person(i) for i in who_ids)

print(f"текст: {caption!r}" + ("  + скріншот" if media else "  (без вкладень)"))
print(f"  час  : {b.human(when)}"
      f"{'   <- часу не було, поставив на 9 ранку' if guessed else ''}")
print(f"  опис : {note!r}\n")

print(f"1) АВТОР ({b.person(AUTHOR)}) одразу бачить у відповідь:\n")
for line in b.confirm(when, 7, who_ids).split("\n"):
    print("   " + line)

kind = "ОДНЕ повідомлення: скрін + підпис + кнопка" if media else "текстове повідомлення"
print(f"\n2) У ЧАС X це отримує {who} — {kind}:\n")

now = datetime.fromisoformat(when)
for i in range(3):
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

n = b.note_of(row)
closed = (f"✅ <s>{n or 'Нагадування'}</s>\n"
          f"закрито · {b.person(388521288)} · {datetime.now(b.TZ):%H:%M}")

print(f"3) {who} тисне «Готово» — повідомлення міняється на:\n")
for line in closed.split("\n"):
    print("   " + line)

print(f"\n4) І ТОДІ автор ({b.person(AUTHOR)}) отримує окремим повідомленням:\n")
for line in closed.split("\n"):
    print("   " + line)

print(f"\n   REMIND_TO={b.REMIND_TO} — автор нагадування не бачить, "
      f"лише звістку про закриття")
