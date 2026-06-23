from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import GOV_POSITIONS, SEP
from database import models as m
from keyboards.main import gov_kb, kb
from utils.formatters import err, h, header, money, ok

router = Router()


class BillForm(StatesGroup):
    title = State()
    text = State()


@router.message(Command("gov"))
async def cmd_gov(message: Message, db: aiosqlite.Connection) -> None:
    user = await m.get_user(db, message.from_user.id)
    if not user["gov_position"] and user["role"] not in {"admin", "owner"}:
        await message.answer(err("доступно только государственным служащим."))
        return
    await message.answer(
        f"{header('🏛 ПРАВИТЕЛЬСТВО США')}\n"
        f"{h(user['gov_position'] or 'Администратор')}\n{SEP}\n"
        "Выберите раздел управления.",
        reply_markup=gov_kb(user["gov_position"]),
    )


@router.callback_query(F.data == "gov:treasury")
async def cb_treasury(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    row = await m.one(db, "SELECT * FROM government_treasury WHERE id=1")
    taxes = await m.all_rows(db, "SELECT * FROM tax_rates ORDER BY type")
    await callback.message.edit_text(f"{header('🏛 КАЗНА')}\nБаланс казны: <b>{money(row['balance'])}</b>\n\n" + "\n".join(f"{h(t['type'])}: {t['rate_percent']}%" for t in taxes))
    await callback.answer()


@router.message(Command("bill"))
async def cmd_bill(message: Message, state: FSMContext) -> None:
    await state.set_state(BillForm.title)
    await message.answer(f"{header('📜 ЗАКОНОПРОЕКТ')}\nВведите название законопроекта.")


@router.message(BillForm.title)
async def form_bill_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(BillForm.text)
    await message.answer("Введите текст законопроекта.")


@router.message(BillForm.text)
async def form_bill_text(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    await db.execute("INSERT INTO laws(title, text, proposed_by) VALUES(?,?,?)", (data["title"], message.text, message.from_user.id))
    await db.commit()
    await state.clear()
    await message.answer(ok("законопроект внесён на рассмотрение."))


@router.message(Command("decree"))
async def cmd_decree(message: Message, db: aiosqlite.Connection) -> None:
    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2:
        await message.answer(err("формат: /decree текст указа"))
        return
    await db.execute("INSERT INTO news_log(type, title, content) VALUES(?,?,?)", ("decree", "Указ правительства", text[1]))
    await db.commit()
    await message.answer(ok("указ опубликован в Вестнике."))


@router.message(Command("emergency"))
async def cmd_emergency(message: Message, db: aiosqlite.Connection) -> None:
    text = (message.text or "").split(maxsplit=1)
    content = text[1] if len(text) > 1 else "В городе объявлено чрезвычайное положение."
    await db.execute("INSERT INTO news_log(type, title, content) VALUES(?,?,?)", ("emergency", "Чрезвычайное положение", content))
    await db.commit()
    await message.answer(f"🚨 <b>Чрезвычайное положение</b>\n{h(content)}")


@router.callback_query(F.data.startswith("gov:"))
async def cb_gov_placeholder(callback: CallbackQuery) -> None:
    names = {
        "gov:decrees": "📋 УКАЗЫ",
        "gov:appoint": "👤 НАЗНАЧЕНИЯ",
        "gov:fines": "⚖️ ШТРАФЫ",
        "gov:stats": "📊 СТАТИСТИКА",
        "gov:votes": "🗳 ГОЛОСОВАНИЕ",
        "gov:bills": "📜 ЗАКОНОПРОЕКТЫ",
        "gov:investigate": "🔍 РАССЛЕДОВАНИЕ",
        "gov:tax": "💰 НАЛОГИ",
        "gov:emergency": "⚠️ ЧП",
    }
    await callback.message.edit_text(f"{header(names.get(callback.data, '🏛 РАЗДЕЛ'))}\nРаздел доступен через команды и административные формы.")
    await callback.answer()
