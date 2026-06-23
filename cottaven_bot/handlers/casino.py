from __future__ import annotations

import random

import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import models as m
from utils.formatters import err, header, money, ok

router = Router()


@router.message(Command("casino"))
async def cmd_casino(message: Message, db: aiosqlite.Connection) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(f"{header('🎰 КАЗИНО')}\nФормат: /casino сумма\nШанс победы: 48%. Выплата: x2.")
        return
    try:
        bet = float(parts[1].replace(",", "."))
    except ValueError:
        await message.answer(err("ставка указана неверно."))
        return
    user = await m.get_user(db, message.from_user.id)
    if bet <= 0 or user["usd_cash"] < bet:
        await message.answer(err("недостаточно наличных для ставки."))
        return
    win = random.random() < 0.48
    payout = bet * 2 if win else 0
    await db.execute("UPDATE users SET usd_cash=usd_cash-?+? WHERE telegram_id=?", (bet, payout, message.from_user.id))
    await db.execute("INSERT INTO casino_log(user_id, game_type, bet, result, payout) VALUES(?,?,?,?,?)", (message.from_user.id, "Кости", bet, "win" if win else "lose", payout))
    await m.log_tx(db, message.from_user.id if not win else None, message.from_user.id if win else None, bet if not win else payout - bet, "USD", "purchase", "Казино")
    await db.commit()
    await message.answer(ok(f"вы выиграли {money(payout - bet)}.") if win else err(f"ставка {money(bet)} проиграна."))
