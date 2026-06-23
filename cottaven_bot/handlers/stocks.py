from __future__ import annotations

import random

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database import models as m
from keyboards.main import kb
from utils.formatters import h, header, money

router = Router()


async def ensure_stocks(db: aiosqlite.Connection) -> None:
    companies = await m.all_rows(db, "SELECT * FROM companies")
    for c in companies:
        exists = await m.one(db, "SELECT id FROM stock_market WHERE company_id=?", (c["id"],))
        if not exists:
            ticker = "".join(ch for ch in c["name"].upper() if ch.isalpha())[:4] or f"C{c['id']}"
            await db.execute("INSERT INTO stock_market(company_id, ticker, price_per_share, total_shares, available_shares) VALUES(?,?,?,?,?)", (c["id"], ticker, random.randint(10, 120), 10000, 10000))
    await db.commit()


@router.message(Command("stocks"))
async def cmd_stocks(message: Message, db: aiosqlite.Connection) -> None:
    await ensure_stocks(db)
    rows = await m.all_rows(db, "SELECT s.*, c.name FROM stock_market s JOIN companies c ON c.id=s.company_id ORDER BY s.ticker")
    text = f"{header('📊 БИРЖА')}\n" + ("\n".join(f"{h(r['ticker'])} · {h(r['name'])} · {money(r['price_per_share'])} · доступно {r['available_shares']}" for r in rows) if rows else "Биржа откроется после появления компаний.")
    await message.answer(text)


@router.callback_query(F.data == "stocks:menu")
async def cb_stocks(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    await ensure_stocks(db)
    rows = await m.all_rows(db, "SELECT s.*, c.name FROM stock_market s JOIN companies c ON c.id=s.company_id ORDER BY s.ticker")
    await callback.message.edit_text(f"{header('📊 БИРЖА')}\n" + ("\n".join(f"{h(r['ticker'])} · {h(r['name'])} · {money(r['price_per_share'])}" for r in rows) if rows else "Биржа откроется после появления компаний."))
    await callback.answer()
