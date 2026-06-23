from __future__ import annotations

import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import models as m
from utils.formatters import h, header, money

router = Router()


@router.message(Command("top"))
async def cmd_top(message: Message, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT *, (usd_cash + usd_bank) AS total FROM users ORDER BY total DESC LIMIT 10")
    lines = []
    for idx, row in enumerate(rows, 1):
        name = await m.user_name(row)
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        lines.append(f"{medal} {h(name)} · {money(row['total'])}")
    await message.answer(f"{header('🏆 ТОП ИГРОКОВ')}\n" + ("\n".join(lines) if lines else "Рейтинг пока пуст."))
