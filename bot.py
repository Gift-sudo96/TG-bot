"""Простий бот-нагадувальник для продажів.

Кидаєш боту скрін або текст, вказуєш коли нагадати — бот нагадає.
"""
import asyncio
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
DEFAULT_HOUR = int(os.environ.get("DEFAULT_HOUR", "10"))
CHECK_EVERY = 30  # секунд між перевірками бази


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
""")
db.commit()


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def human(iso_str):
    """ISO-рядок з бази (UTC) -> '19.08 14:30' у місцевому часі."""
    return datetime.fromisoformat(iso_str).astimezone(TZ).strftime("%d.%m %H:%M")


# --------------------------------------------------------------- розбір часу

UNITS = {
    "хв": timedelta(minutes=1), "х": timedelta(minutes=1),
    "г": timedelta(hours=1), "год": timedelta(hours=1),
    "д": timedelta(days=1), "дн": timedelta(days=1),
    "т": timedelta(weeks=1), "тиж": timedelta(weeks=1),
    "міс": timedelta(days=30),
}
WEEKDAYS = {
    "пн": 0, "понеділок": 0, "вт": 1, "вівторок": 1, "ср": 2, "середа": 2,
    "чт": 3, "четвер": 3, "пт": 4, "пятниця": 4, "п'ятниця": 4,
    "сб": 5, "субота": 5, "нд": 6, "неділя": 6,
}


def parse_when(text):
    """Шукає строк на ПОЧАТКУ тексту.

    Повертає (ISO-рядок у UTC | None, залишок тексту як нотатка).
    """
    t = (text or "").strip()
    if not t:
        return None, ""
    now = datetime.now(TZ)

    def at(dt, h, m):
        return dt.replace(hour=h, minute=m, second=0, microsecond=0)

    # +3д / 2г / 30хв / 1міс
    m = re.match(r"^\+?(\d+)\s*(міс|тиж|хв|год|дн|д|г|т|х)\.?", t, re.I)
    if m:
        return iso(now + int(m.group(1)) * UNITS[m.group(2).lower()]), t[m.end():].strip()

    # завтра / післязавтра [10:00]
    m = re.match(r"^(післязавтра|завтра)(?:\s+(\d{1,2}):(\d{2}))?", t, re.I)
    if m:
        days = 2 if m.group(1).lower() == "післязавтра" else 1
        h, mi = (int(m.group(2)), int(m.group(3))) if m.group(2) else (DEFAULT_HOUR, 0)
        return iso(at(now + timedelta(days=days), h, mi)), t[m.end():].strip()

    # 15.09 / 15.09.2026 / 15.09 14:30  (точка = дата, двокрапка = час)
    m = re.match(r"^(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?:\s+(\d{1,2}):(\d{2}))?", t)
    if m:
        d, mo, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        h, mi = (int(m.group(4)), int(m.group(5))) if m.group(4) else (DEFAULT_HOUR, 0)
        if 1 <= d <= 31 and 1 <= mo <= 12 and 0 <= h <= 23 and 0 <= mi <= 59:
            year = now.year
            if yr:
                year = int(yr) + 2000 if len(yr) == 2 else int(yr)
            try:
                dt = now.replace(year=year, month=mo, day=d, hour=h, minute=mi,
                                 second=0, microsecond=0)
            except ValueError:
                return None, t
            if dt <= now and not yr:      # дата вже минула -> наступний рік
                dt = dt.replace(year=year + 1)
            return iso(dt), t[m.end():].strip()

    # пн / пт 9:00
    m = re.match(r"^([а-яіїєґ']{2,10})(?:\s+(\d{1,2}):(\d{2}))?", t, re.I)
    if m and m.group(1).lower() in WEEKDAYS:
        target = WEEKDAYS[m.group(1).lower()]
        h, mi = (int(m.group(2)), int(m.group(3))) if m.group(2) else (DEFAULT_HOUR, 0)
        ahead = (target - now.weekday()) % 7 or 7
        return iso(at(now + timedelta(days=ahead), h, mi)), t[m.end():].strip()

    # 14:30 -> сьогодні, або завтра якщо вже минуло
    m = re.match(r"^(\d{1,2}):(\d{2})", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            dt = at(now, h, mi)
            if dt <= now:
                dt += timedelta(days=1)
            return iso(dt), t[m.end():].strip()

    return None, t


# --------------------------------------------------------------- клавіатури

def kb_choose(rid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 день", callback_data=f"set:{rid}:1"),
         InlineKeyboardButton(text="3 дні", callback_data=f"set:{rid}:3")],
        [InlineKeyboardButton(text="7 днів", callback_data=f"set:{rid}:7"),
         InlineKeyboardButton(text="30 днів", callback_data=f"set:{rid}:30")],
        [InlineKeyboardButton(text="✖ Не треба", callback_data=f"drop:{rid}")],
    ])


def kb_remind(rid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Готово", callback_data=f"done:{rid}"),
        InlineKeyboardButton(text="⏰ +1 день", callback_data=f"snz:{rid}:1"),
        InlineKeyboardButton(text="⏰ +7 днів", callback_data=f"snz:{rid}:7"),
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
    "Кинь скрін або текст і на <b>початку підпису</b> вкажи, коли нагадати:\n"
    "<code>+3д Іван, 1500 грн, передзвонити</code>\n"
    "<code>15.09 14:30 продовжити підписку</code>\n"
    "<code>завтра 10:00 надіслати рахунок</code>\n"
    "<code>пт передзвонити Олені</code>\n\n"
    "Формати строку: <code>30хв</code> <code>2г</code> <code>3д</code> "
    "<code>2тиж</code> <code>1міс</code> <code>15.09</code> "
    "<code>15.09 14:30</code> <code>завтра</code> <code>пн 9:00</code> "
    "<code>14:30</code>\n\n"
    "Якщо строк не вказати — бот сам запитає кнопками.\n\n"
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
        lines.append(f"<code>#{r['id']}</code>  {human(r['remind_at'])}  "
                     f"{(r['note'] or '—')[:60]}")
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


@dp.message(F.reply_to_message, F.text)
async def reply_with_time(m: Message):
    """Відповідь на питання «коли нагадати?» задає строк для чернетки."""
    if not allowed(m.from_user.id):
        return
    row = db.execute(
        "SELECT * FROM reminders WHERE prompt_msg_id=? AND status='draft'",
        (m.reply_to_message.message_id,)).fetchone()
    if row is None:
        return await catch_all(m)
    when, note = parse_when(m.text)
    if when is None:
        return await m.answer("Не зрозумів строк. Напр.: <code>3д</code>, "
                              "<code>15.09 14:30</code>, <code>завтра 10:00</code>")
    db.execute("UPDATE reminders SET remind_at=?, status='pending', note=? WHERE id=?",
               (when, note or row["note"], row["id"]))
    db.commit()
    await m.answer(f"✅ Нагадаю <b>{human(when)}</b>  <code>#{row['id']}</code>")


@dp.message(F.photo | F.document | F.video | F.text)
async def catch_all(m: Message):
    if not allowed(m.from_user.id):
        return await m.answer(f"Немає доступу. Твій ID: <code>{m.from_user.id}</code>")

    when, note = parse_when(m.caption or m.text or "")

    cur = db.execute(
        "INSERT INTO reminders (creator_id, creator_name, src_chat_id, src_msg_id,"
        " note, created_at, remind_at, status) VALUES (?,?,?,?,?,?,?,?)",
        (m.from_user.id, uname(m), m.chat.id, m.message_id, note,
         iso(now_utc()), when, "pending" if when else "draft"))
    db.commit()
    rid = cur.lastrowid

    if when:
        return await m.reply(f"✅ Нагадаю <b>{human(when)}</b>  <code>#{rid}</code>")

    prompt = await m.reply(
        "Коли нагадати? Обери кнопку або <b>відповідай на це повідомлення</b> "
        "часом — напр. <code>15.09 14:30</code>",
        reply_markup=kb_choose(rid))
    db.execute("UPDATE reminders SET prompt_msg_id=? WHERE id=?", (prompt.message_id, rid))
    db.commit()


@dp.callback_query(F.data.startswith("set:"))
async def cb_set(c: CallbackQuery):
    _, rid, days = c.data.split(":")
    when = iso(now_utc() + timedelta(days=int(days)))
    db.execute("UPDATE reminders SET remind_at=?, status='pending' WHERE id=?", (when, rid))
    db.commit()
    await c.message.edit_text(f"✅ Нагадаю <b>{human(when)}</b>  <code>#{rid}</code>")
    await c.answer()


@dp.callback_query(F.data.startswith("drop:"))
async def cb_drop(c: CallbackQuery):
    rid = c.data.split(":")[1]
    db.execute("UPDATE reminders SET status='cancelled' WHERE id=?", (rid,))
    db.commit()
    await c.message.edit_text("Скасовано.")
    await c.answer()


@dp.callback_query(F.data.startswith("done:"))
async def cb_done(c: CallbackQuery):
    rid = c.data.split(":")[1]
    db.execute("UPDATE reminders SET status='done' WHERE id=?", (rid,))
    db.commit()
    await c.message.edit_text(f"✅ Закрито  <code>#{rid}</code>")
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

async def send_reminder(r):
    head = (f"⏰ <b>Нагадування</b>  <code>#{r['id']}</code>\n"
            f"{r['note'] or '(без опису)'}\n"
            f"<i>створено {human(r['created_at'])} · {r['creator_name']}</i>")
    for chat_id in targets(r["creator_id"]):
        try:
            await bot.send_message(chat_id, head, reply_markup=kb_remind(r["id"]))
            if r["src_msg_id"]:
                await bot.copy_message(chat_id, r["src_chat_id"], r["src_msg_id"])
        except Exception:
            log.exception("не вдалось надіслати нагадування #%s у чат %s", r["id"], chat_id)


async def reminder_loop():
    while True:
        try:
            due = db.execute(
                "SELECT * FROM reminders WHERE status='pending' AND remind_at IS NOT NULL"
                " AND remind_at <= ? ORDER BY remind_at", (iso(now_utc()),)).fetchall()
            for r in due:
                # позначаємо до відправки, щоб при збої не надсилати по колу
                db.execute("UPDATE reminders SET status='sent' WHERE id=?", (r["id"],))
                db.commit()
                await send_reminder(r)

            # прибираємо чернетки, для яких строк так і не вказали
            db.execute("DELETE FROM reminders WHERE status='draft' AND created_at < ?",
                       (iso(now_utc() - timedelta(days=2)),))
            db.commit()
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
