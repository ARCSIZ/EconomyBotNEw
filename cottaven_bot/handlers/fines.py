from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database import models as m
from handlers.start import send_sensitive_callback, send_sensitive_or_answer
from keyboards.main import kb
from utils.formatters import dt, err, header, h, money, ok

router = Router()


async def fines_text(db: aiosqlite.Connection, user_id: int) -> str:
    rows = await m.all_rows(db, "SELECT * FROM fines WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (user_id,))
    if not rows:
        return f"{header('🚫 ШТРАФЫ')}\nАктивных и архивных штрафов пока нет."
    lines = []
    for row in rows:
        state = {"pending": "ожидает оплаты", "paid": "оплачен", "cancelled": "отменён"}.get(row["status"], row["status"])
        lines.append(f"№{row['id']} · {money(row['amount'])} · {state}\nПричина: {h(row['reason'])}\nДата: {dt(row['created_at'])}")
    return f"{header('🚫 ШТРАФЫ')}\n" + "\n\n".join(lines)


@router.message(Command("fines"))
async def cmd_fines(message: Message, db: aiosqlite.Connection) -> None:
    text = await fines_text(db, message.from_user.id)
    buttons = [[(f"Оплатить №{r['id']}", f"finepay:{r['id']}")] for r in await m.all_rows(db, "SELECT id FROM fines WHERE user_id=? AND status='pending' LIMIT 5", (message.from_user.id,))]
    markup = kb(buttons) if buttons else None
    if await send_sensitive_or_answer(message, text, reply_markup=markup):
        return
    await message.reply(text, reply_markup=markup) if message.chat.type in {"group", "supergroup"} else await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "fines:menu")
async def cb_fines(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT id FROM fines WHERE user_id=? AND status='pending' LIMIT 5", (callback.from_user.id,))
    text = await fines_text(db, callback.from_user.id)
    markup = kb([[(f"Оплатить №{r['id']}", f"finepay:{r['id']}")] for r in rows]) if rows else None
    if await send_sensitive_callback(callback, text, reply_markup=markup):
        return
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("finepay:"))
async def cb_pay_fine(callback: CallbackQuery) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Оплата штрафов доступна только в личных сообщениях с ботом.", show_alert=True)
        return
    fine_id = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"{header('🚫 ОПЛАТА ШТРАФА')}\nВыберите источник оплаты для штрафа №{fine_id}.",
        reply_markup=kb([[("🏦 Банк", f"finepaybank:{fine_id}"), ("💵 Наличные", f"finepaycash:{fine_id}")]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("finepaybank:") | F.data.startswith("finepaycash:"))
async def cb_pay_fine_source(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    source = "bank" if callback.data.startswith("finepaybank:") else "cash"
    fine_id = int(callback.data.split(":")[1])
    problem = await m.pay_fine(db, callback.from_user.id, fine_id, source)
    await callback.message.edit_text(err(problem) if problem else ok(f"штраф №{fine_id} оплачен."))
    await callback.answer()
