"""Перевірка того, кому саме йде нагадування.

    venv\\Scripts\\python.exe test_routing.py
"""
import bot as b

SERHII, ARINA, THIRD = 547696309, 388521288, 100000003

CASES = [
    # (REMIND_TO, хто в списку, автор, очікувані одержувачі, пояснення)
    ("others", {SERHII, ARINA}, SERHII, [ARINA],
     "написав Сергій -> бачить Аріна"),
    ("others", {SERHII, ARINA}, ARINA, [SERHII],
     "написала Аріна -> бачить Сергій"),
    ("others", {SERHII, ARINA, THIRD}, SERHII, sorted([ARINA, THIRD]),
     "троє: бачать усі, крім автора"),
    ("others", {SERHII}, SERHII, [SERHII],
     "у списку лише автор -> нагадування не має зникнути"),
    ("others", set(), SERHII, [SERHII],
     "список порожній -> шлемо авторові"),
    ("all", {SERHII, ARINA}, SERHII, sorted([SERHII, ARINA]),
     "REMIND_TO=all -> обом разом з автором"),
    ("author", {SERHII, ARINA}, SERHII, [SERHII],
     "REMIND_TO=author -> лише авторові"),
]

keep_to, keep_allowed = b.REMIND_TO, b.ALLOWED
ok = bad = 0
for mode, allowed, author, want, why in CASES:
    b.REMIND_TO, b.ALLOWED = mode, allowed
    got = b.targets(author)
    if got == want:
        ok += 1
        print(f"  OK   {why}")
    else:
        bad += 1
        print(f"  ПОМИЛКА  {why}\n         очікував {want}, отримав {got}")

# автор ніколи не має отримати нагадування, коли є кому його показати
b.REMIND_TO = "others"
for allowed in ({SERHII, ARINA}, {SERHII, ARINA, THIRD}):
    for author in allowed:
        b.ALLOWED = allowed
        if author in b.targets(author):
            bad += 1
            print(f"  ПОМИЛКА  автор {author} потрапив у одержувачі {allowed}")
            break
    else:
        continue
    break
else:
    ok += 1
    print("  OK   автор не потрапляє в одержувачі, поки є кому показати")

b.REMIND_TO, b.ALLOWED = keep_to, keep_allowed
print(f"\n{ok} пройшло, {bad} впало")
