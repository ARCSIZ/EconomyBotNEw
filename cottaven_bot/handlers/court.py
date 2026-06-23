from __future__ import annotations

import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import models as m
from utils.formatters import err, h, header, ok

router = Router()


@router.message(Command("court"))
async def cmd_court(message: Message, db: aiosqlite.Connection) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        rows = await m.all_rows(db, "SELECT * FROM court_cases WHERE plaintiff_id=? OR defendant_id=? ORDER BY id DESC LIMIT 10", (message.from_user.id, message.from_user.id))
        text = f"{header('⚖️ СУД')}\n" + ("\n".join(f"№{r['id']} · {h(r['status'])} · {h(r['description'])}" for r in rows) if rows else "Судебных дел пока нет.\nФормат: /court @user описание")
        await message.answer(text)
        return
    target = await m.find_user(db, parts[1])
    if not target:
        await message.answer(err("ответчик не найден."))
        return
    await db.execute("INSERT INTO court_cases(plaintiff_id, defendant_id, description) VALUES(?,?,?)", (message.from_user.id, target["telegram_id"], parts[2]))
    await db.commit()
    await message.answer(ok("исковое заявление принято в суд."))
