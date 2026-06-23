from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import BUSINESS_TYPES
from database import models as m
from keyboards.main import kb
from utils.formatters import h, header, money, ok, err

router = Router()


class BusinessBuy(StatesGroup):
    typ = State()
    name = State()


@router.message(Command("market"))
async def cmd_market(message: Message) -> None:
    rows = [[(f"{name} · {money(price)}", f"bizbuy:{name}")] for name, (price, income) in BUSINESS_TYPES.items()]
    text = f"{header('🛒 РЫНОК БИЗНЕСОВ')}\n" + "\n".join(f"{h(name)} · цена {money(price)} · доход {money(income)}/час" for name, (price, income) in BUSINESS_TYPES.items())
    await message.answer(text, reply_markup=kb(rows[:10]))


@router.message(Command("businesses"))
async def cmd_businesses(message: Message, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM businesses WHERE owner_id=? ORDER BY id", (message.from_user.id,))
    if not rows:
        await message.answer(f"{header('🏪 МОИ БИЗНЕСЫ')}\nУ вас пока нет бизнеса.", reply_markup=kb([[("🛒 Рынок бизнесов", "business:market")]]))
        return
    text = f"{header('🏪 МОИ БИЗНЕСЫ')}\n" + "\n\n".join(f"№{r['id']} · <b>{h(r['name'])}</b>\nТип: {h(r['type'])} · уровень {r['level']} · доход {money(r['income_per_hour'])}/час" for r in rows)
    kb_rows = []
    for r in rows[:5]:
        kb_rows.append([(f"💰 Собрать №{r['id']}", f"bizcollect:{r['id']}"), ("🗑 Удалить", f"bizdelete:{r['id']}")])
    await message.answer(text, reply_markup=kb(kb_rows))


@router.callback_query(F.data == "business:market")
async def cb_market(callback: CallbackQuery) -> None:
    await callback.message.edit_text(f"{header('🛒 РЫНОК БИЗНЕСОВ')}\nВыберите тип бизнеса.", reply_markup=kb([[(name, f"bizbuy:{name}")] for name in BUSINESS_TYPES.keys()]))
    await callback.answer()


@router.callback_query(F.data.startswith("bizbuy:"))
async def cb_bizbuy(callback: CallbackQuery, state: FSMContext) -> None:
    typ = callback.data.split(":", 1)[1]
    await state.update_data(typ=typ)
    await state.set_state(BusinessBuy.name)
    await callback.message.edit_text(f"{header('🛒 ПОКУПКА БИЗНЕСА')}\nТип: {h(typ)}\nВведите название бизнеса.")
    await callback.answer()


@router.message(BusinessBuy.name)
async def form_biz_name(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    problem = await m.buy_business(db, message.from_user.id, message.text or data["typ"], data["typ"])
    await state.clear()
    await message.answer(err(problem) if problem else ok("бизнес приобретён."))


@router.callback_query(F.data.startswith("bizcollect:"))
async def cb_bizcollect(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    problem = await m.collect_business_income(db, callback.from_user.id, int(callback.data.split(":")[1]))
    await callback.message.edit_text(err(problem) if problem else ok("доход бизнеса собран."))
    await callback.answer()


@router.callback_query(F.data.startswith("bizdelete:"))
async def cb_bizdelete(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    business_id = int(callback.data.split(":")[1])
    row = await m.one(db, "SELECT * FROM businesses WHERE id=?", (business_id,))
    if not row or row["owner_id"] != callback.from_user.id:
        await callback.answer("Удалять бизнес может только владелец.", show_alert=True)
        return
    await callback.message.edit_text(
        f"{header('🗑 УДАЛЕНИЕ БИЗНЕСА')}\n"
        f"№{row['id']} · <b>{h(row['name'])}</b>\nТип: {h(row['type'])}\n\n"
        "Вы уверены, что хотите удалить бизнес? Деньги не возвращаются.",
        reply_markup=kb([[("✅ Да, удалить", f"bizdelete:confirm:{business_id}"), ("⬅️ Назад", "businesses:menu")]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bizdelete:confirm:"))
async def cb_bizdelete_confirm(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    business_id = int(callback.data.split(":")[2])
    problem = await m.safe_delete_business(db, business_id, callback.from_user.id)
    if problem:
        await callback.answer(problem, show_alert=True)
        return
    await callback.message.edit_text(ok("бизнес удалён."))
    await callback.answer("Готово.")
