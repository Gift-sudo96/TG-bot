"""Розбір часу з довільного тексту.

Шукає згадку часу будь-де в реченні, а не лише на початку.
Все, що не є часом, повертається як опис нагадування.

    "фіскалізувати оплату в 5к. завтра в 10.00"
        -> завтра 10:00, опис "фіскалізувати оплату в 5к."
    "завтра"              -> завтра 09:00, опис порожній
    "скільки лишилось?"   -> None (бот поставить на 9 ранку)
"""
import re
from datetime import datetime, timedelta

__all__ = ["parse", "DEFAULT_HOUR"]

DEFAULT_HOUR = 9           # коли вказали день без часу
MORNING, NOON, EVENING, NIGHT = 9, 13, 18, 22

MONTHS = {
    "січн": 1, "янва": 1, "лют": 2, "февра": 2, "берез": 3, "март": 3,
    "квіт": 4, "апрел": 4, "трав": 5, "мая": 5, "май": 5, "черв": 6,
    "июн": 6, "июл": 7, "лип": 7, "серп": 8, "август": 8, "вересн": 9,
    "верес": 9, "сентя": 9, "жовт": 10, "октя": 10, "листопад": 11,
    "нояб": 11, "груд": 12, "декаб": 12,
}
WEEKDAYS = {
    "понеділ": 0, "понедельн": 0, "пн": 0,
    "вівтор": 1, "вторн": 1, "вт": 1,
    "серед": 2, "сред": 2, "ср": 2,
    "четвер": 3, "чт": 3,
    "п'ятниц": 4, "пятниц": 4, "пятниць": 4, "пт": 4,
    "субот": 5, "суббот": 5, "сб": 5,
    "неділ": 6, "воскресен": 6, "нд": 6, "вс": 6,
}

# ---------------------------------------------------------------- допоміжне

def _key(word, table):
    """Знаходить значення в таблиці за початком слова (щоб ловити відмінки)."""
    w = word.lower().replace("’", "'").replace("`", "'")
    for stem, val in table.items():
        if w.startswith(stem):
            return val
    return None


_UNITS = (r"хвилин\w*|хвил\w*|мин\w*|хв|"
          r"годин\w*|год|час(?:а|ов|ів)?|г|"
          r"тижн\w*|тижд\w*|недел\w*|тиж|т|"
          r"місяц\w*|мес\w*|міс|"
          r"днів|дні|день|дня|добу|доби|дн|д")


def _unit_kind(s):
    s = s.lower()
    for pref, kind in (("хв", "min"), ("хвил", "min"), ("мин", "min"),
                       ("годин", "hour"), ("год", "hour"), ("час", "hour"),
                       ("тижн", "week"), ("тижд", "week"), ("тиж", "week"),
                       ("недел", "week"), ("місяц", "month"), ("міс", "month"),
                       ("мес", "month"), ("дн", "day"), ("ден", "day"),
                       ("дня", "day"), ("доб", "day")):
        if s.startswith(pref):
            return kind
    return {"г": "hour", "т": "week", "д": "day"}.get(s)


def _delta(n, kind):
    return {"min": timedelta(minutes=n), "hour": timedelta(hours=n),
            "day": timedelta(days=n), "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n)}[kind]


# ------------------------------------------------------------------ шаблони

PREP = r"(?:о|об|у|в|на|до)"

RE_REL_NUM = re.compile(
    r"(?<![\w.,])(?:(о|об|у|в|на)\s+)?(через\s+|за\s+|\+)?"
    r"(\d{1,4})(\s*)(" + _UNITS + r")(?![\wа-яіїєґ])", re.I)
RE_REL_WORD = re.compile(
    r"через\s+(хвилину|півгодини|годину|день|добу|тиждень|неділю|місяць|"
    r"минуту|час|неделю|месяц)", re.I)

RE_NAMED_DAY = re.compile(
    r"(?<![\wа-яіїєґ])(післязавтра|позавчора|сьогодні|сегодня|завтра|"
    r"післязавтру|послезавтра)(?![\wа-яіїєґ])", re.I)
RE_WEEKDAY = re.compile(
    r"(?<![\wа-яіїєґ])(?:(?:у|в|на)\s+)?(наступн\w+\s+)?"
    r"(понеділ\w*|понедельн\w*|вівтор\w*|вторн\w*|серед\w*|сред\w*|четвер\w*|"
    r"п['’`]?ятниц\w*|субот\w*|суббот\w*|неділ\w*|воскресен\w*|"
    r"пн|вт|ср|чт|пт|сб|нд)(?![\wа-яіїєґ])", re.I)
RE_DMY = re.compile(
    r"(?<![\d.])(\d{1,2})\s*[./]\s*(\d{1,2})(?:\s*[./]\s*(\d{2,4}))?(?![\d])")
RE_D_MONTH = re.compile(
    r"(?<![\d])(\d{1,2})\s*(?:го|-го)?\s+"
    r"(січн\w*|янва\w*|лют\w*|февра\w*|берез\w*|март\w*|квіт\w*|апрел\w*|"
    r"трав\w*|ма[йя]\w*|черв\w*|июн\w*|лип\w*|июл\w*|серп\w*|август\w*|"
    r"вересн\w*|верес\w*|сентя\w*|жовт\w*|октя\w*|листопад\w*|нояб\w*|"
    r"груд\w*|декаб\w*)", re.I)

RE_HHMM = re.compile(
    r"(?:(" + PREP + r")\s+)?(?<![\d])(\d{1,2})\s*[:.\-]\s*(\d{2})(?![\d])")
# "о 9" — завжди час. "на 3", "в 12" — час лише коли в тексті вже є день
# ("завтра в 12"), інакше це радше "рахунок на 3 позиції".
RE_H_STRICT = re.compile(
    r"(?:(о|об)\s+)(?<![\d])(\d{1,2})(?![\d])(\s*годин\w*|\s*год)?"
    r"(?![\wа-яіїєґ])", re.I)
RE_H_LOOSE = re.compile(
    r"(?:(" + PREP + r")\s+)(?<![\d])(\d{1,2})(?![\d])(\s*годин\w*|\s*год)?"
    r"(?![\wа-яіїєґ])", re.I)
RE_H_WORD = re.compile(
    r"(?<![\d])(\d{1,2})(?![\d])\s*(?:годині|годин|год)(?![\wа-яіїєґ])", re.I)
RE_DAYPART = re.compile(
    r"(?<![\wа-яіїєґ])(вранці|зранку|ранку|ранком|утра|вдень|дня|обід|"
    r"опівдні|ввечері|увечері|вечора|вечором|вночі|ночі|опівночі)"
    r"(?![\wа-яіїєґ])", re.I)

DAYPART_HOUR = {
    "вранці": MORNING, "зранку": MORNING, "ранку": MORNING,
    "ранком": MORNING, "утра": MORNING,
    "вдень": NOON, "дня": NOON, "обід": NOON, "опівдні": 12,
    "ввечері": EVENING, "увечері": EVENING, "вечора": EVENING,
    "вечором": EVENING,
    "вночі": NIGHT, "ночі": NIGHT, "опівночі": 0,
}
MORNING_WORDS = {"вранці", "зранку", "ранку", "ранком", "утра"}
NIGHT_WORDS = {"вночі", "ночі"}


def _apply_part(h, part_word, bare):
    """Переводить у 24-годинний формат за словом-уточненням.

    "о 7 вечора" -> 19, "о 3 ночі" -> 3, "о 9 ранку" -> 9.
    Без уточнення "о 3" означає 15:00 — о третій ночі нагадувань не ставлять.
    """
    if part_word in MORNING_WORDS:
        return h
    if part_word in NIGHT_WORDS:
        return h if h <= 4 else (h + 12 if h < 12 else h)
    if part_word is not None:                 # день / обід / вечір
        return h + 12 if h < 12 else h
    return h + 12 if bare and 1 <= h <= 7 else h


# -------------------------------------------------------------------- розбір

class _Spans:
    """Збирає з'їдені шматки тексту, щоб потім вирізати їх з опису."""

    def __init__(self):
        self.items = []

    def add(self, m, group=0):
        self.items.append((m.start(group), m.end(group)))

    def taken(self, pos):
        return any(a <= pos < b for a, b in self.items)

    def cut(self, text):
        out, last = [], 0
        for a, b in sorted(self.items):
            if a >= last:
                out.append(text[last:a])
                last = b
            else:
                last = max(last, b)
        out.append(text[last:])
        return _clean("".join(out))


def _clean(s):
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.!?;:])", r"\1", s)
    s = re.sub(r"([,.;:])\s*(?=[,.;:])", "", s)
    s = re.sub(r"(?<![\wа-яіїєґ])(о|об|у|в|на|до|і|та)\s*$", "", s, flags=re.I)
    s = re.sub(r"^\s*[,.;:!?\-–—]+\s*", "", s)
    s = re.sub(r"\s*[,;:\-–—]+\s*$", "", s)
    return s.strip()


def _find_relative(text, spans):
    m = RE_REL_WORD.search(text)
    if m:
        word = m.group(1).lower()
        kind = ("min" if word.startswith(("хвилин", "минут")) else
                "hour" if word.startswith(("годин", "час")) else
                "day" if word.startswith(("день", "добу")) else
                "week" if word.startswith(("тижд", "тижн", "недел", "неділ")) else
                "month")
        spans.add(m)
        return _delta(1, kind) if word != "півгодини" else timedelta(minutes=30)

    for m in RE_REL_NUM.finditer(text):
        prep, prefix = m.group(1), m.group(2)
        num, gap, unit = int(m.group(3)), m.group(4), m.group(5)
        kind = _unit_kind(unit)
        if kind is None:
            continue
        # однобуквене скорочення без "через"/"+" приймаємо лише впритул
        # до числа: "3д" це три дні, а "2 т" радше дві тисячі
        if not prefix and len(unit) == 1 and gap:
            continue
        # "о 12 годині" — це показник годинника, а не тривалість.
        # А от "на 3 дні" — саме тривалість, тому день/тиждень пропускаємо далі.
        if prep and not prefix and kind in ("hour", "min"):
            continue
        if num == 0 or num > 999:
            continue
        spans.add(m)
        return _delta(num, kind)
    return None


def _find_day(text, now, spans):
    """Повертає дату (без часу) або None."""
    m = RE_NAMED_DAY.search(text)
    if m:
        w = m.group(1).lower()
        shift = 2 if w.startswith(("післязавтр", "послезавтра")) else \
                0 if w.startswith(("сьогодні", "сегодня")) else 1
        spans.add(m)
        return now.date() + timedelta(days=shift)

    m = RE_D_MONTH.search(text)
    if m:
        d, mon = int(m.group(1)), _key(m.group(2), MONTHS)
        if mon and 1 <= d <= 31:
            spans.add(m)
            return _safe_date(now, now.year, mon, d, roll=True)

    for m in RE_DMY.finditer(text):
        if spans.taken(m.start()):
            continue
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        # "10.00" чи "14.30" це час, а не дата: місяця 0 і 30 не існує
        if not y and (b == 0 or b > 12):
            continue
        if not (1 <= a <= 31 and 1 <= b <= 12):
            continue
        year = now.year if not y else (int(y) + 2000 if len(y) == 2 else int(y))
        spans.add(m)
        return _safe_date(now, year, b, a, roll=not y)

    m = RE_WEEKDAY.search(text)
    if m:
        wd = _key(m.group(2), WEEKDAYS)
        if wd is not None:
            spans.add(m)
            ahead = (wd - now.weekday()) % 7 or 7
            if m.group(1):                       # "наступного понеділка"
                ahead += 7 if ahead <= 7 else 0
            return now.date() + timedelta(days=ahead)
    return None


def _safe_date(now, year, mon, day, roll):
    try:
        d = now.replace(year=year, month=mon, day=day).date()
    except ValueError:
        return None
    if roll and d < now.date():
        try:
            d = d.replace(year=year + 1)
        except ValueError:
            pass
    return d


def _find_time(text, spans, day_found=False):
    """Повертає (година, хвилина) або None."""
    part_m = RE_DAYPART.search(text)
    word = part_m.group(1).lower() if part_m else None

    def done(h, mi, bare):
        spans.add(part_m) if part_m else None
        return _apply_part(h, word, bare), mi

    # явні години з хвилинами: "14:30", "в 10.00" — heuristics не застосовуємо
    for m in RE_HHMM.finditer(text):
        if spans.taken(m.start(2)):
            continue
        h, mi = int(m.group(2)), int(m.group(3))
        if h > 23 or mi > 59:
            continue
        spans.add(m)
        return done(h, mi, bare=False)

    for m in RE_H_WORD.finditer(text):
        if spans.taken(m.start(1)):
            continue
        h = int(m.group(1))
        if h <= 23:
            spans.add(m)
            return done(h, 0, bare=True)

    for m in (RE_H_LOOSE if day_found else RE_H_STRICT).finditer(text):
        if spans.taken(m.start(2)):
            continue
        h = int(m.group(2))
        if h <= 23:
            spans.add(m)
            return done(h, 0, bare=True)

    if part_m:
        spans.add(part_m)
        return DAYPART_HOUR[word], 0
    return None


def parse(text, now):
    """text + поточний час -> (datetime | None, опис).

    now має бути aware-datetime у місцевій таймзоні.
    """
    raw = (text or "").strip()
    if not raw:
        return None, ""
    low = raw.lower().replace("’", "'").replace("`", "'")
    spans = _Spans()

    rel = _find_relative(low, spans)
    if rel is not None:
        return (now + rel).replace(second=0, microsecond=0), spans.cut(raw)

    day = _find_day(low, now, spans)
    tm = _find_time(low, spans, day_found=day is not None)

    if day is None and tm is None:
        return None, raw

    if tm is None:
        h, mi = DEFAULT_HOUR, 0
    else:
        h, mi = tm

    if day is None:
        dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if dt <= now:                    # час уже минув -> завтра
            dt += timedelta(days=1)
    else:
        dt = now.replace(year=day.year, month=day.month, day=day.day,
                         hour=h, minute=mi, second=0, microsecond=0)
    return dt, spans.cut(raw)
