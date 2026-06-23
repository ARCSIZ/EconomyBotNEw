from __future__ import annotations

import math

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database import models as m
from handlers.start import send_sensitive_callback, send_sensitive_or_answer
from keyboards.main import kb
from utils.formatters import dt, header, h, money, page_nav

router = Router()

FILTERS = {
    "all": ("Все", ""),
    "plus": ("Пополнения", "AND change_amount > 0"),
    "minus": ("Списания", "AND change_amount < 0"),
    "salary": ("Зарплаты", "AND reason LIKE '%зарплат%'"),
    "fine": ("Штрафы", "AND reason LIKE '%штраф%'"),
    "tax": ("Налоги", "AND reason LIKE '%налог%'"),
    "rent": ("Аренда", "AND reason LIKE '%аренд%'"),
    "crypto": ("Крипто", "AND currency IN ('BTC','ETH','USDT')"),
}


async def history_text(db: aiosqlite.Connection, user_id: int, key: str = "all", page: int = 0) -> tuple[str, int]:
    label, clause = FILTERS.get(key, FILTERS["all"])
    count = await m.one(db, f"SELECT COUNT(*) AS c FROM balance_history WHERE user_id=? {clause}", (user_id,))
    total_pages = max(math.ceil((count["c"] if count else 0) / 10), 1)
    page = max(0, min(page, total_pages - 1))
    rows = await m.all_rows(
        db,
        f"SELECT * FROM balance_history WHERE user_id=? {clause} ORDER BY id DESC LIMIT 10 OFFSET ?",
        (user_id, page * 10),
    )
    if not rows:
        return f"{header('📈 ИСТОРИЯ БАЛАНСА')}\nФильтр: {label}\nЗаписей пока нет.", total_pages
    lines = []
    for row in rows:
        sign = "+" if row["change_amount"] >= 0 else ""
        amount = money(row["change_amount"]) if row["currency"] == "USD" else f"{sign}{row['change_amount']:g} {row['currency']}"
        lines.append(f"{dt(row['created_at'])} · {sign}{amount} · {h(row['reason'])} · баланс после: {row['balance_after']:g}")
    return f"{header('📈 ИСТОРИЯ БАЛАНСА')}\nФильтр: {label}\n" + "\n".join(lines) + "\n" + page_nav(page, total_pages), total_pages


def history_kb(key: str, page: int, total: int):
    nav = []
    if page > 0:
        nav.append(("◀️ Назад", f"history:{key}:{page - 1}"))
    if page + 1 < total:
        nav.append(("Вперёд ▶️", f"history:{key}:{page + 1}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.extend([
        [("Все", "history:all:0"), ("Пополнения", "history:plus:0"), ("Списания", "history:minus:0")],
        [("Зарплаты", "history:salary:0"), ("Штрафы", "history:fine:0"), ("Налоги", "history:tax:0")],
    ])
    return kb(rows)


@router.message(Command("history"))
async def cmd_history(message: Message, db: aiosqlite.Connection) -> None:
    text, total = await history_text(db, message.from_user.id)
    if await send_sensitive_or_answer(message, text, reply_markup=history_kb("all", 0, total)):
        return
    await message.reply(text, reply_markup=history_kb("all", 0, total)) if message.chat.type in {"group", "supergroup"} else await message.answer(text, reply_markup=history_kb("all", 0, total))


@router.callback_query(F.data.startswith("history:"))
async def cb_history(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    _, key, page = callback.data.split(":")
    text, total = await history_text(db, callback.from_user.id, key, int(page))
    if await send_sensitive_callback(callback, text, reply_markup=history_kb(key, int(page), total)):
        return
    await callback.message.edit_text(text, reply_markup=history_kb(key, int(page), total))
    await callback.answer()
