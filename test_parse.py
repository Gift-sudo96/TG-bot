"""Швидка перевірка розбору строків. Запуск: python test_parse.py"""
from datetime import datetime
from zoneinfo import ZoneInfo

from bot import TZ, parse_when

CASES = [
    "+3д Іван, 1500 грн, передзвонити",
    "3д без плюса",
    "30хв тест",
    "2г зателефонувати",
    "2тиж",
    "1міс продовжити підписку",
    "15.09 14:30 продовжити",
    "15.09 без часу",
    "01.01 новий рік (мало перескочити на наступний рік)",
    "15.09.2027 з роком",
    "завтра",
    "завтра 09:15 рахунок",
    "післязавтра дзвінок",
    "пт передзвонити Олені",
    "пн 9:00 планерка",
    "п'ятниця з апострофом",
    "14:30 сьогодні або завтра",
    "просто текст без часу",
    "40.99 некоректна дата",
    "",
]

print("зараз:", datetime.now(TZ).strftime("%d.%m.%Y %H:%M %A"), "\n")
for c in CASES:
    when, note = parse_when(c)
    if when:
        local = datetime.fromisoformat(when).astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    else:
        local = "— (запитає кнопками)"
    print(f"{c!r:<55} -> {local:<20} note={note!r}")
