"""Перевірка щоденного повтору нагадувань.

    venv\\Scripts\\python.exe test_repeat.py
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import bot as b

TZ = ZoneInfo("Europe/Kyiv")


def at(day, hour, minute=0):
    return datetime(2026, 8, day, hour, minute, tzinfo=TZ)


CASES = [
    # (коли мало спрацювати, "зараз", очікуваний наступний показ, пояснення)
    (at(20, 11), at(20, 11, 0), at(21, 11), "спрацювало вчасно -> завтра о тій же"),
    (at(20, 11), at(20, 11, 0, ), at(21, 11), "секунда в секунду теж переносить"),
    (at(20, 11), at(20, 23), at(21, 11), "спрацювало пізно ввечері -> завтра"),
    (at(20, 11), at(23, 9), at(23, 11), "бот лежав 3 доби -> найближчий майбутній"),
    (at(20, 11), at(23, 12), at(24, 11), "лежав 3 доби, час сьогодні вже минув"),
    (at(20, 11), at(20, 10, 59), at(20, 11), "ще не час -> лишається як було"),
]

ok = bad = 0
for remind_at, now, want, why in CASES:
    got = b.next_occurrence(b.iso(remind_at), now)
    if got.astimezone(TZ) == want:
        ok += 1
        print(f"  OK   {why}")
    else:
        bad += 1
        print(f"  ПОМИЛКА  {why}")
        print(f"         очікував {want}, отримав {got.astimezone(TZ)}")

# ніколи не має повертати минуле — інакше нагадування зациклиться
now = at(22, 15)
for d in range(1, 20):
    for h in range(0, 24, 5):
        nxt = b.next_occurrence(b.iso(at(d, h)), now)
        if nxt <= now:
            bad += 1
            print(f"  ПОМИЛКА  {at(d, h)} дало минуле {nxt}")
            break
else:
    ok += 1
    print("  OK   жоден варіант не повертає минулий час (зациклення неможливе)")

print(f"\n{ok} пройшло, {bad} впало")
