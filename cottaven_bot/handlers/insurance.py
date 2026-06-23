from __future__ import annotations

from datetime import datetime, timedelta

import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import models as m
from utils.formatters import err, h, header, money, ok

router = Router()


@router.message(Command("insurance"))
async def cmd_insurance(message: Message, db: aiosqlite.Connection) -> None:
    parts = (message.text or "").split()
    if len(parts) == 1:
        rows = await m.all_rows(db, "SELECT * FROM insurance_policies WHERE user_id=? ORDER BY id DESC", (message.from_user.id,))
        text = f"{header('🛡 СТРАХОВКА')}\n" + ("\n".join(f"№{r['id']} · {h(r['type'])} · покрытие {money(r['coverage'])} · статус {h(r['status'])}" for r in rows) if rows else "Полисов пока нет.\nФормат: /insurance vehicle 1")
        await message.answer(text)
        return
    typ = parts[1]
    object_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    premium = 500
    user = await m.get_user(db, message.from_user.id)
    if user["usd_bank"] < premium:
        await message.answer(err("недостаточно средств для оплаты полиса."))
        return
    expires = (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds")
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (premium, message.from_user.id))
    await db.execute("INSERT INTO insurance_policies(user_id, type, object_id, premium, coverage, expires_at) VALUES(?,?,?,?,?,?)", (message.from_user.id, typ, object_id, premium, 5000, expires))
    await db.commit()
    await message.answer(ok("страховой полис оформлен на 30 дней."))
