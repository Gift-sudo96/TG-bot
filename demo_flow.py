"""Показує, що саме бот відповість на конкретний підпис. Нічого не змінює."""
import sys
from datetime import datetime

import bot as b

caption = sys.argv[1] if len(sys.argv) > 1 else "завтра в 10.00"
when, note = b.parse_when(caption)

print(f"підпис до скріна: {caption!r}\n")
print(f"  розпізнаний час : {b.human(when) if when else '— (буде питати кнопками)'}")
print(f"  опис у базі     : {note!r}")
print(f"  статус          : {'pending' if when else 'draft'}")
print(f"\n1) ОДРАЗУ бот відповідає у відповідь на твій скрін:\n")
print("   " + (b.confirm(when, 7) if when else "Коли нагадати? [кнопки]"))

if when:
    row = {"id": 7, "note": note, "created_at": b.iso(datetime.now(b.TZ)),
           "creator_name": "@Gift_sudo96", "src_msg_id": 1, "src_chat_id": 1,
           "creator_id": 547696309}
    head = (f"⏰ <b>Нагадування</b>  <code>#{row['id']}</code>\n"
            f"{row['note'] or '(без опису)'}\n"
            f"<i>створено {b.human(row['created_at'])} · {row['creator_name']}</i>")
    print(f"\n2) У ЧАС X приходить це + копія самого скріна:\n")
    for line in head.split("\n"):
        print("   " + line)
    print("   [✅ Готово] [⏰ +1 день] [⏰ +7 днів]")
    print(f"\n3) Кому прийде: {b.targets(row['creator_id'])}")
    print(f"   NOTIFY_ALL={b.NOTIFY_ALL}")
