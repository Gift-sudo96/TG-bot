"""Перевірка того, що кілька фото в одному повідомленні дають ОДНЕ нагадування.

Telegram надсилає альбом кількома окремими повідомленнями з однаковим
media_group_id. Тут ми це імітуємо, без звернень до Telegram.

    venv/bin/python test_album.py
"""
import asyncio
import os
import tempfile

os.environ.setdefault("BOT_TOKEN", "123456789:AAEEfaketokenfaketokenfaketokenfake1")
os.environ.setdefault("ALLOWED_IDS", "547696309,388521288")
_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "t.db")
os.environ["LOG_PATH"] = os.path.join(_tmp, "t.log")

import bot as b

b.MEDIA_GROUP_WAIT = 0.3        # щоб тест не тягнувся


class FakeUser:
    def __init__(self, uid=547696309):
        self.id = uid
        self.username = "Serhii_Gift"
        self.full_name = self.first_name = "Serhii"


class FakeChat:
    def __init__(self, cid=111):
        self.id = cid


class FakeMsg:
    """Мінімум полів, які читає бот."""

    def __init__(self, mid, caption=None, text=None, photo=True, group=None):
        self.message_id = mid
        self.caption = caption
        self.text = text
        self.photo = [object()] if photo else None
        self.document = self.video = self.animation = None
        self.audio = self.voice = self.video_note = None
        self.media_group_id = group
        self.from_user = FakeUser()
        self.chat = FakeChat()
        self.answers = []

    async def reply(self, text, **kw):
        self.answers.append(text)

    async def answer(self, text, **kw):
        self.answers.append(text)


def last_row():
    return b.db.execute("SELECT * FROM reminders ORDER BY id DESC LIMIT 1").fetchone()


def count():
    return b.db.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]


async def main():
    ok = bad = 0

    def check(cond, label, extra=""):
        nonlocal ok, bad
        if cond:
            ok += 1
            print(f"  OK   {label}")
        else:
            bad += 1
            print(f"  ПОМИЛКА  {label}{('  ' + extra) if extra else ''}")

    # --- альбом із трьох фото, підпис лише на другому (так робить Telegram)
    before = count()
    album = [FakeMsg(101, group="g1"),
             FakeMsg(102, caption="через 2 дні фіскалізувати оплату", group="g1"),
             FakeMsg(103, group="g1")]
    for m in album:
        await b.catch_album(m)
    await asyncio.sleep(b.MEDIA_GROUP_WAIT + 0.3)

    check(count() == before + 1, "три фото -> одне нагадування, а не три",
          f"створено {count() - before}")
    r = last_row()
    check(b.media_ids(r) == [101, 102, 103], "запамʼятались усі три фото",
          f"отримав {b.media_ids(r)}")
    check(r["note"] == "фіскалізувати оплату", "підпис знайдено на другому фото",
          f"отримав {r['note']!r}")
    check("Вкладень: 3" in album[0].answers[0], "у підтвердженні сказано про 3 вкладення")
    check(len(album[0].answers) == 1 and not album[1].answers,
          "підтвердження надіслано один раз, а не на кожне фото")

    # --- альбом без підпису взагалі
    before = count()
    album2 = [FakeMsg(201, group="g2"), FakeMsg(202, group="g2")]
    for m in album2:
        await b.catch_album(m)
    await asyncio.sleep(b.MEDIA_GROUP_WAIT + 0.3)
    r = last_row()
    check(count() == before + 1, "альбом без підпису теж дає одне нагадування")
    check(b.media_ids(r) == [201, 202], "обидва фото збережені")
    check(r["remind_at"] and b.hhmm(r["remind_at"]) == "09:00",
          "без часу ставиться на 9 ранку")

    # --- фото приходять не по порядку
    before = count()
    album3 = [FakeMsg(303, group="g3"), FakeMsg(301, caption="завтра", group="g3"),
              FakeMsg(302, group="g3")]
    for m in album3:
        await b.catch_album(m)
    await asyncio.sleep(b.MEDIA_GROUP_WAIT + 0.3)
    r = last_row()
    check(b.media_ids(r) == [301, 302, 303], "порядок фото відновлено",
          f"отримав {b.media_ids(r)}")

    # --- одне фото як і раніше
    before = count()
    single = FakeMsg(401, caption="завтра о 14:00 передзвонити")
    await b.create_reminder([single])
    r = last_row()
    check(count() == before + 1, "одне фото -> одне нагадування")
    check(b.media_ids(r) == [401], "одне вкладення")
    check("Вкладень" not in single.answers[0],
          "для одного фото про кількість не пишемо")

    # --- звичайний текст без вкладень
    before = count()
    plain = FakeMsg(501, text="через 3 дні подзвонити", photo=False)
    await b.create_reminder([plain])
    r = last_row()
    check(b.media_ids(r) == [], "текст без фото не тягне за собою копію")

    print(f"\n{ok} пройшло, {bad} впало")
    return bad


raise SystemExit(asyncio.run(main()))
