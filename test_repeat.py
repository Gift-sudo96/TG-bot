"""Перевірка повторів нагадування, якому не натиснули «Готово».

Правило: кожні 4 години в межах 9:00-21:00, далі наступного дня о 9:00.

    venv\\Scripts\\python.exe test_repeat.py
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import bot as b

TZ = ZoneInfo("Europe/Kyiv")


def at(day, hour, minute=0):
    return datetime(2026, 8, day, hour, minute, tzinfo=TZ)


CASES = [
    # (спрацювало, "зараз", наступний показ, пояснення)
    (at(20, 11), at(20, 11), at(20, 15), "11:00 -> +4 год"),
    (at(20, 15), at(20, 15), at(20, 19), "15:00 -> +4 год"),
    (at(20, 19), at(20, 19), at(21, 9), "19:00 -> 23:00 запізно -> завтра 9:00"),
    (at(20, 17), at(20, 17), at(20, 21), "17:00 -> рівно 21:00 ще можна"),
    (at(20, 21), at(20, 21), at(21, 9), "21:00 -> 1:00 зарано -> завтра 9:00"),
    (at(20, 9), at(20, 9), at(20, 13), "ранковий цикл 9 -> 13"),
    (at(20, 11, 30), at(20, 11, 30), at(20, 15, 30), "неповна година зберігається"),
    (at(20, 19, 30), at(20, 19, 30), at(21, 9), "19:30 -> 23:30 запізно -> завтра"),
    (at(20, 23), at(20, 23), at(21, 9), "нічне нагадування -> ранок"),
    (at(20, 11), at(23, 10), at(23, 13), "бот лежав 3 доби -> найближчий у майбутньому"),
    (at(20, 11), at(23, 22), at(24, 9), "лежав 3 доби, вже вечір -> завтра зранку"),
    (at(25, 11), at(20, 12), at(25, 11), "час ще не настав -> без змін"),
]

ok = bad = 0
for remind_at, now, want, why in CASES:
    got = b.next_occurrence(b.iso(remind_at), now).astimezone(TZ)
    if got == want:
        ok += 1
        print(f"  OK   {why}")
    else:
        bad += 1
        print(f"  ПОМИЛКА  {why}\n         очікував {want}, отримав {got}")

# інваріанти: ніколи не минуле і ніколи поза межами робочого дня
now = at(22, 15, 17)
for d in range(18, 26):
    for h in range(24):
        nxt = b.next_occurrence(b.iso(at(d, h)), now).astimezone(TZ)
        if nxt <= now:
            bad += 1
            print(f"  ПОМИЛКА  {at(d, h)} дало минуле {nxt}")
            break
        # вихідний час користувача поважаємо, а от перенесені — в межах дня
        if nxt != at(d, h) and not (b.DAY_START <= nxt.hour <= b.DAY_END):
            bad += 1
            print(f"  ПОМИЛКА  {at(d, h)} дало поза межами дня: {nxt}")
            break
    else:
        continue
    break
else:
    ok += 1
    print("  OK   ніколи не минуле і ніколи поза 9:00-21:00")

# 9:00 за замовчуванням, коли часу не вказали взагалі
nine = b.next_nine()
ok_nine = nine.hour == b.DAY_START and nine.minute == 0 and nine > datetime.now(TZ)
print(f"  {'OK  ' if ok_nine else 'ПОМИЛКА'} next_nine() -> {nine:%d.%m %H:%M}")
ok, bad = (ok + 1, bad) if ok_nine else (ok, bad + 1)

print(f"\n{ok} пройшло, {bad} впало")
