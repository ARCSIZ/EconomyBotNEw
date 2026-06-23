from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import VEHICLES
from database import models as m
from keyboards.main import kb
from utils.formatters import err, h, header, money, ok

router = Router()


@router.message(Command("vehicles"))
async def cmd_vehicles(message: Message, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM vehicles WHERE owner_id=? ORDER BY id", (message.from_user.id,))
    owned = "\n".join(f"№{r['id']} · {h(r['brand'])} {h(r['model'])} · номер <code>{h(r['plate_number'])}</code>" for r in rows) or "У вас пока нет транспорта."
    await message.answer(f"{header('🚗 ТРАНСПОРТ')}\n{owned}", reply_markup=kb([[(name, f"vehbuy:{name}")] for name in VEHICLES.keys()]))


@router.callback_query(F.data == "vehicles:menu")
async def cb_vehicles(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM vehicles WHERE owner_id=? ORDER BY id", (callback.from_user.id,))
    owned = "\n".join(f"№{r['id']} · {h(r['brand'])} {h(r['model'])} · номер <code>{h(r['plate_number'])}</code>" for r in rows) or "У вас пока нет транспорта."
    await callback.message.edit_text(f"{header('🚗 ТРАНСПОРТ')}\n{owned}", reply_markup=kb([[(name, f"vehbuy:{name}")] for name in VEHICLES.keys()]))
    await callback.answer()


@router.callback_query(F.data.startswith("vehbuy:"))
async def cb_vehicle_buy(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    problem = await m.buy_vehicle(db, callback.from_user.id, callback.data.split(":", 1)[1])
    await callback.message.edit_text(err(problem) if problem else ok("транспорт зарегистрирован на ваше имя."))
    await callback.answer()
