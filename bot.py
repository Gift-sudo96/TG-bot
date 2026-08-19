"""Простий бот-нагадувальник для продажів.

Кидаєш боту скрін або текст, вказуєш коли нагадати — бот нагадає.
"""
import asyncio
import html
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

import timeparse

# ---------------------------------------------------------------- налаштування

def _load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            # прибираємо пробіли, \r від Windows і лапки, якщо їх дописали
            os.environ.setdefault(k.strip(), v.strip().strip("\"'").strip())

_load_env()

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ALLOWED = {int(x) for x in re.findall(r"-?\d+", os.environ.get("ALLOWED_IDS", ""))}
NOTIFY_ALL = os.environ.get("NOTIFY_ALL", "true").lower() in ("1", "true", "yes")
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Europe/Kyiv"))
DEFAULT_HOUR = int(os.environ.get("DEFAULT_HOUR", "9"))
DAY_START = int(os.environ.get("DAY_START", "9"))    # раніше не турбуємо
DAY_END = int(os.environ.get("DAY_END", "21"))       # пізніше теж
REPEAT_HOURS = int(os.environ.get("REPEAT_HOURS", "4"))
CHECK_EVERY = 30  # секунд між перевірками бази

# "547696309:Сергій,388521288:Аріна" -> {547696309: "Сергій", ...}
NAMES = {}
for _pair in os.environ.get("NAMES", "").split(","):
    _id, _, _name = _pair.partition(":")
    if _id.strip().isdigit() and _name.strip():
        NAMES[int(_id.strip())] = _name.strip()

timeparse.DEFAULT_HOUR = DEFAULT_HOUR   # "завтра" без часу -> ця година


def check_token(token):
    """Зрозуміла помилка замість стектрейсу, якщо токен зіпсований."""
    if not token:
        raise SystemExit(
            "\n  У файлі .env не заповнений BOT_TOKEN.\n"
            "  Візьми токен у @BotFather: /mybots -> твій бот -> API Token\n")
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
        raise SystemExit(
            f"\n  BOT_TOKEN у файлі .env виглядає неправильно.\n"
            f"  Зараз там {len(token)} символів і {token.count(':')} двокрапок.\n\n"
            f"  Правильний вигляд — одне ціле значення від @BotFather:\n"
            f"    BOT_TOKEN=8123456789:AAH8xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            f"    (10 цифр, ОДНА двокрапка, 35 символів, без лапок і пробілів)\n\n"
            f"  Найчастіша помилка: токен вставили ПОРУЧ із заготовкою,\n"
            f"  а не замість неї. Видали все після BOT_TOKEN= і встав заново.\n\n"
            f"  Де взяти: @BotFather -> /mybots -> твій бот -> API Token\n")


check_token(TOKEN)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"),
              logging.StreamHandler()],
)
log = logging.getLogger("bot")

# ------------------------------------------------------------------------ база

db = sqlite3.connect("reminders.db", check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS reminders (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id     INTEGER NOT NULL,
  creator_name   TEXT,
  src_chat_id    INTEGER,
  src_msg_id     INTEGER,
  note           TEXT DEFAULT '',
  created_at     TEXT NOT NULL,
  remind_at      TEXT,
  status         TEXT NOT NULL DEFAULT 'draft',
  prompt_msg_id  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_due ON reminders(status, remind_at);

-- які повідомлення бот надіслав по кожному нагадуванню, щоб при
-- натисканні "Готово" оновити їх усі, а не лише те, де натиснули
CREATE TABLE IF NOT EXISTS sent (
  reminder_id INTEGER NOT NULL,
  chat_id     INTEGER NOT NULL,
  message_id  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sent ON sent(reminder_id);
""")
if "times_sent" not in {c[1] for c in db.execute("PRAGMA table_info(reminders)")}:
    db.execute("ALTER TABLE reminders ADD COLUMN times_sent INTEGER DEFAULT 0")
db.commit()


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def human(iso_str):
    """ISO-рядок з бази (UTC) -> '19.08 14:30' у місцевому часі.

    Рік дописується, лише якщо він не поточний — щоб не засмічувати.
    """
    dt = datetime.fromisoformat(iso_str).astimezone(TZ)
    fmt = "%d.%m %H:%M" if dt.year == datetime.now(TZ).year else "%d.%m.%Y %H:%M"
    return dt.strftime(fmt)


def hhmm(iso_str):
    """ISO-рядок з бази (UTC) -> '11:00' у місцевому часі."""
    return datetime.fromisoformat(iso_str).astimezone(TZ).strftime("%H:%M")


def next_nine():
    """Найближча 9:00 ранку — коли час нагадування не вказали взагалі."""
    now = datetime.now(TZ)
    dt = now.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    return dt if dt > now else dt + timedelta(days=1)


def _step(dt):
    """Один крок повтору: +4 години, але не поза межами 9:00-21:00."""
    local = (dt + timedelta(hours=REPEAT_HOURS)).astimezone(TZ)
    late = local.hour > DAY_END or (local.hour == DAY_END and
                                    (local.minute or local.second))
    if late:                                     # після 21:00 -> завтра зранку
        local += timedelta(days=1)
    if late or local.hour < DAY_START:           # до 9:00 -> сьогодні о 9:00
        local = local.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def next_occurrence(iso_str, now):
    """Коли показати нагадування наступного разу.

    Поки не натиснули «Готово», нагадування повертається кожні
    REPEAT_HOURS годин у межах дня, а після DAY_END — наступного ранку.
    Якщо бот лежав кілька діб, перескакуємо одразу в майбутнє, щоб не
    сипати пропущеними нагадуваннями поспіль.
    """
    nxt = datetime.fromisoformat(iso_str)
    for _ in range(10000):                       # запобіжник від зациклення
        if nxt > now:
            break
        nxt = _step(nxt)
    return nxt


def person(uid, fallback=""):
    """Імʼя для підпису: спершу з NAMES, інакше з профілю Telegram."""
    return NAMES.get(uid) or fallback or str(uid)


def in_words(delta):
    """timedelta -> 'через 25 хв' / 'через 3 год' / 'через 12 дн.'"""
    mins = int(delta.total_seconds() // 60)
    if mins < 60:
        return f"через {max(mins, 1)} хв"
    if mins < 60 * 24:
        return f"через {mins // 60} год"
    return f"через {mins // (60 * 24)} дн."


def confirm(when, rid):
    """Текст підтвердження після створення нагадування."""
    dt = datetime.fromisoformat(when).astimezone(TZ)
    now = datetime.now(TZ)
    if dt <= now:
        return (f"⚠️ <b>{human(when)}</b> — цей час уже минув, нагадаю одразу. "
                f"Якщо помилка, зроби <code>/cancel {rid}</code>")
    return f"✅ Нагадаю <b>{human(when)}</b> ({in_words(dt - now)})  <code>#{rid}</code>"


# --------------------------------------------------------------- розбір часу
# Уся логіка розпізнавання часу живе в timeparse.py, там же її тести
# (test_parse.py). Тут лише перевід у UTC для бази.

def parse_when(text):
    """Текст -> (ISO-рядок у UTC | None, опис без згадки часу)."""
    dt, note = timeparse.parse(text, datetime.now(TZ))
    return (iso(dt) if dt else None), note



# --------------------------------------------------------------- клавіатури

def kb_remind(rid):
    """Відкладати вручну не треба — нагадування саме повертається щодня."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Готово", callback_data=f"done:{rid}"),
    ]])


# ----------------------------------------------------------------------- бот

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def allowed(uid):
    return not ALLOWED or uid in ALLOWED


def targets(creator_id):
    """Кому надсилати нагадування."""
    if NOTIFY_ALL and ALLOWED:
        return sorted(ALLOWED)
    return [creator_id]


def uname(m):
    u = m.from_user
    return ("@" + u.username) if u.username else (u.full_name or str(u.id))


HELP = (
    "<b>Як користуватись</b>\n\n"
    "Кинь скрін або просто напиши текст — і десь у ньому згадай, коли нагадати. "
    "Де саме згадаєш, не має значення:\n\n"
    "<code>завтра</code>\n"
    "<code>фіскалізувати оплату в 5к. завтра в 10.00</code>\n"
    "<code>передзвонити Олені через 2 години</code>\n"
    "<code>15 вересня продовжити підписку</code>\n"
    "<code>в понеділок о 9 планерка</code>\n\n"
    "Решта тексту стане описом нагадування.\n\n"
    "<b>Що розуміє</b>\n"
    "• <code>завтра</code> <code>післязавтра</code> <code>сьогодні</code>\n"
    "• <code>в пн</code> <code>у п'ятницю</code> <code>наступного вівторка</code>\n"
    "• <code>15.09</code> <code>15.09.2027</code> <code>15 вересня</code>\n"
    "• <code>о 14:30</code> <code>в 10.00</code> <code>о 12 годині</code> "
    "<code>о 7 вечора</code> <code>вранці</code>\n"
    "• <code>через 2 години</code> <code>через тиждень</code> "
    "<code>+3д</code> <code>30хв</code>\n\n"
    "Великі чи малі букви — байдуже.\n\n"
    "<b>Якщо часу не вказати</b> — нагадаю <b>завтра о 9:00</b>. "
    "Щоб перенести, просто напиши те саме ще раз із часом.\n\n"
    "<b>Поки не натиснули «Готово»</b> нагадування повертається кожні "
    "4 години, але тільки з 9:00 до 21:00. Пізно ввечері не турбує — "
    "переносить на наступний ранок.\n\n"
    "<b>Команди</b>\n"
    "/list — активні нагадування\n"
    "/cancel 12 — скасувати нагадування №12\n"
    "/id — мій Telegram ID\n"
)


@dp.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"Твій ID: <code>{m.from_user.id}</code>\n"
                   f"Додай його в <code>ALLOWED_IDS</code> у файлі .env")


@dp.message(Command("start", "help"))
async def cmd_start(m: Message):
    if not allowed(m.from_user.id):
        return await m.answer(f"Немає доступу. Твій ID: <code>{m.from_user.id}</code>")
    await m.answer(HELP)


@dp.message(Command("list"))
async def cmd_list(m: Message):
    if not allowed(m.from_user.id):
        return
    rows = db.execute(
        "SELECT * FROM reminders WHERE status='pending' ORDER BY remind_at").fetchall()
    if not rows:
        return await m.answer("Активних нагадувань немає.")
    lines = ["<b>Активні нагадування</b>"]
    for r in rows:
        again = f"  ({r['times_sent']}-й раз)" if (r["times_sent"] or 0) > 1 else ""
        lines.append(f"<code>#{r['id']}</code>  {human(r['remind_at'])}  "
                     f"{(r['note'] or '—')[:60]}{again}")
    lines.append("\nСкасувати: <code>/cancel НОМЕР</code>")
    await m.answer("\n".join(lines))


@dp.message(Command("cancel"))
async def cmd_cancel(m: Message):
    if not allowed(m.from_user.id):
        return
    nums = re.findall(r"\d+", m.text or "")
    if not nums:
        return await m.answer("Вкажи номер: <code>/cancel 12</code>")
    rid = int(nums[0])
    cur = db.execute(
        "UPDATE reminders SET status='cancelled' WHERE id=? AND status='pending'", (rid,))
    db.commit()
    await m.answer(f"Нагадування #{rid} скасовано." if cur.rowcount
                   else f"Нагадування #{rid} не знайдено серед активних.")


@dp.message(F.photo | F.document | F.video | F.text)
async def catch_all(m: Message):
    if not allowed(m.from_user.id):
        return await m.answer(f"Немає доступу. Твій ID: <code>{m.from_user.id}</code>")

    when, note = parse_when(m.caption or m.text or "")
    guessed = when is None
    if guessed:                      # часу в тексті немає -> завтра о 9:00
        when = iso(next_nine())

    # копіюємо оригінал лише коли там є що показувати. Для звичайного
    # тексту опис уже все несе, і друге повідомлення було б дублем.
    media = bool(m.photo or m.document or m.video or m.animation
                 or m.audio or m.voice or m.video_note)

    cur = db.execute(
        "INSERT INTO reminders (creator_id, creator_name, src_chat_id, src_msg_id,"
        " note, created_at, remind_at, status) VALUES (?,?,?,?,?,?,?,'pending')",
        (m.from_user.id, uname(m), m.chat.id, m.message_id if media else None, note,
         iso(now_utc()), when))
    db.commit()
    rid = cur.lastrowid

    text = confirm(when, rid)
    if guessed:
        text += "\nЧасу не було вказано. Інший — просто напиши ще раз із ним."
    await m.reply(text)


@dp.callback_query(F.data.startswith("done:"))
async def cb_done(c: CallbackQuery):
    rid = int(c.data.split(":")[1])
    row = db.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    db.execute("UPDATE reminders SET status='done' WHERE id=?", (rid,))
    db.commit()

    note = note_of(row) if row else ""
    closer = html.escape(person(c.from_user.id, c.from_user.first_name))
    text = (f"✅ <s>{note}</s>" if note else "✅ <s>Нагадування</s>")
    text += f"\nзакрито · {closer} · {datetime.now(TZ):%H:%M}"

    # оновлюємо всі копії, щоб і друга людина побачила, що справу закрито
    was_photo = bool(row and row["src_msg_id"])
    for s in db.execute("SELECT * FROM sent WHERE reminder_id=?", (rid,)).fetchall():
        try:
            if was_photo:     # у фото редагується підпис, а не текст
                await bot.edit_message_caption(chat_id=s["chat_id"],
                                               message_id=s["message_id"],
                                               caption=text,
                                               parse_mode=ParseMode.HTML)
            else:
                await bot.edit_message_text(text, chat_id=s["chat_id"],
                                            message_id=s["message_id"])
        except Exception:
            pass          # повідомлення могли видалити або воно вже таке саме
    db.execute("DELETE FROM sent WHERE reminder_id=?", (rid,))
    db.commit()
    await c.answer("Готово")


@dp.callback_query(F.data.startswith("snz:"))
async def cb_snooze(c: CallbackQuery):
    _, rid, days = c.data.split(":")
    when = iso(now_utc() + timedelta(days=int(days)))
    db.execute("UPDATE reminders SET remind_at=?, status='pending' WHERE id=?", (when, rid))
    db.commit()
    await c.message.edit_text(f"⏰ Відкладено до <b>{human(when)}</b>  <code>#{rid}</code>")
    await c.answer()


# ------------------------------------------------------- цикл нагадувань

def note_of(r):
    """Опис нагадування, безпечний для HTML і обрізаний під ліміт підпису."""
    return html.escape((r["note"] or "").strip())[:700]


def reminder_text(r):
    """Суть окремим рядком, під нею сірим час, автор і лічильник повторів."""
    note = note_of(r)
    who = html.escape(person(r["creator_id"], r["creator_name"]))
    meta = f"на {hhmm(r['remind_at'])} · {who}"
    n = (r["times_sent"] or 0) + 1
    if n > 1:                       # повтори частіші за добу, тому рахуємо рази
        meta += f" · 🔁 {n}-й раз"
    return (f"⏰ <b>{note}</b>" if note else "⏰ <b>Нагадування</b>") + "\n" + meta


async def send_reminder(r):
    text = reminder_text(r)
    kb = kb_remind(r["id"])
    for chat_id in targets(r["creator_id"]):
        mid = None
        try:
            if r["src_msg_id"]:
                # скрін і підпис одним повідомленням, щоб кнопка явно
                # належала саме цьому скріну, а не висіла окремо над ним
                res = await bot.copy_message(chat_id, r["src_chat_id"], r["src_msg_id"],
                                             caption=text, parse_mode=ParseMode.HTML,
                                             reply_markup=kb)
                mid = res.message_id
            else:
                mid = (await bot.send_message(chat_id, text, reply_markup=kb)).message_id
        except Exception:
            log.exception("не вдалось надіслати #%s у чат %s", r["id"], chat_id)
            try:            # оригінал могли видалити — доставимо хоча б текст
                mid = (await bot.send_message(chat_id, text, reply_markup=kb)).message_id
            except Exception:
                log.exception("і текстом теж не вийшло: #%s -> %s", r["id"], chat_id)
        if mid:
            db.execute("INSERT INTO sent (reminder_id, chat_id, message_id) VALUES (?,?,?)",
                       (r["id"], chat_id, mid))
            db.commit()


async def reminder_loop():
    while True:
        try:
            now = now_utc()
            due = db.execute(
                "SELECT * FROM reminders WHERE status='pending' AND remind_at IS NOT NULL"
                " AND remind_at <= ? ORDER BY remind_at", (iso(now),)).fetchall()
            for r in due:
                # Нагадування повертається щодня, поки його не закриють кнопкою
                nxt = next_occurrence(r["remind_at"], now)
                db.execute("UPDATE reminders SET remind_at=?, times_sent=times_sent+1"
                           " WHERE id=?", (iso(nxt), r["id"]))
                db.commit()
                await send_reminder(r)

        except Exception:
            log.exception("помилка в циклі нагадувань")
        await asyncio.sleep(CHECK_EVERY)


async def main():
    if not TOKEN:
        raise SystemExit("Немає BOT_TOKEN. Створи файл .env — див. .env.example")
    if not ALLOWED:
        log.warning("ALLOWED_IDS порожній — боту може писати будь-хто! "
                    "Напиши боту /id і додай свій ID у .env")
    log.info("старт; дозволені ID: %s; NOTIFY_ALL=%s", ALLOWED or "всі", NOTIFY_ALL)
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
