from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import REAL_ESTATE
from database import models as m
from keyboards.main import kb
from utils.formatters import err, h, header, money, ok

router = Router()


@router.message(Command("realestate"))
async def cmd_realestate(message: Message, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM real_estate WHERE owner_id=? ORDER BY id", (message.from_user.id,))
    owned = "\n\n".join(f"№{r['id']} · <b>{h(r['name'])}</b>\nРайон: {h(r['district'])} · аренда {money(r['rent_price'])}" for r in rows) or "У вас пока нет недвижимости."
    market = [[(f"{name} · {money(item[2])}", f"estatebuy:{name}")] for name, item in REAL_ESTATE.items()]
    await message.answer(f"{header('🏠 НЕДВИЖИМОСТЬ')}\n{owned}", reply_markup=kb(market))


@router.callback_query(F.data == "realestate:menu")
async def cb_realestate(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM real_estate WHERE owner_id=? ORDER BY id", (callback.from_user.id,))
    owned = "\n\n".join(f"№{r['id']} · <b>{h(r['name'])}</b>\nРайон: {h(r['district'])} · аренда {money(r['rent_price'])}" for r in rows) or "У вас пока нет недвижимости."
    await callback.message.edit_text(f"{header('🏠 НЕДВИЖИМОСТЬ')}\n{owned}", reply_markup=kb([[(name, f"estatebuy:{name}")] for name in REAL_ESTATE.keys()]))
    await callback.answer()


@router.callback_query(F.data.startswith("estatebuy:"))
async def cb_estate_buy(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    problem = await m.buy_real_estate(db, callback.from_user.id, callback.data.split(":", 1)[1])
    await callback.message.edit_text(err(problem) if problem else ok("объект недвижимости приобретён."))
    await callback.answer()
