"""Перевіряє, чи бот може писати кожному з ALLOWED_IDS.

Нічого нікому не надсилає — лише питає Telegram про чат.
Запуск: venv\\Scripts\\python.exe check_access.py
"""
import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import bot as b


async def main():
    tg = Bot(b.TOKEN)
    print(f"NOTIFY_ALL={b.NOTIFY_ALL} -> нагадування йдуть "
          f"{'усім зі списку' if b.NOTIFY_ALL else 'лише автору'}\n")
    for uid in sorted(b.ALLOWED):
        try:
            chat = await tg.get_chat(uid)
            name = chat.full_name or chat.title or "?"
            uname = f" @{chat.username}" if chat.username else ""
            print(f"  {uid}  ✅ доступний — {name}{uname}")
        except TelegramAPIError as e:
            print(f"  {uid}  ❌ НЕДОСТУПНИЙ — {e.message}")
            print(f"          ця людина ще не натискала /start у бота,")
            print(f"          тому нагадування їй НЕ дійде")
    await tg.session.close()


asyncio.run(main())
