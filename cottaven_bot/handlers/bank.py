from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database import models as m
from handlers.start import send_sensitive_callback, send_sensitive_or_answer
from keyboards.main import bank_kb, kb
from utils.formatters import dt, err, header, h, money, ok

router = Router()


class PayForm(StatesGroup):
    target = State()
    amount = State()


class DepositForm(StatesGroup):
    amount = State()
    days = State()


class LoanForm(StatesGroup):
    amount = State()
    months = State()


async def bank_text(db: aiosqlite.Connection, user_id: int) -> str:
    user = await m.get_user(db, user_id)
    card = await m.one(db, "SELECT card_number FROM bank_cards WHERE user_id=? ORDER BY id LIMIT 1", (user_id,))
    deposits = await m.one(db, "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS s FROM deposits WHERE user_id=? AND status='active'", (user_id,))
    loans = await m.one(db, "SELECT COUNT(*) AS c, COALESCE(SUM(remaining),0) AS s FROM loans WHERE user_id=? AND status!='paid'", (user_id,))
    return (
        f"{header('🏦 БАНК COTTAVEN', 'Los Angeles · CA')}\n"
        f"💳 Карта: <code>{h(card['card_number']) if card else '—'}</code>\n"
        f"🏦 Счёт: <b>{money(user['usd_bank'])}</b>\n"
        f"💵 Наличные: <b>{money(user['usd_cash'])}</b>\n"
        f"📈 Активные вклады: {deposits['c']} · {money(deposits['s'])}\n"
        f"💸 Кредиты: {loans['c']} · {money(loans['s'])}"
    )


@router.message(Command("bank"))
async def cmd_bank(message: Message, db: aiosqlite.Connection) -> None:
    text = await bank_text(db, message.from_user.id)
    if await send_sensitive_or_answer(message, text, reply_markup=bank_kb()):
        return
    await message.reply(text, reply_markup=bank_kb()) if message.chat.type in {"group", "supergroup"} else await message.answer(text, reply_markup=bank_kb())


@router.callback_query(F.data == "bank:menu")
async def cb_bank(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    text = await bank_text(db, callback.from_user.id)
    if await send_sensitive_callback(callback, text, reply_markup=bank_kb()):
        return
    await callback.message.edit_text(text, reply_markup=bank_kb())
    await callback.answer()


@router.callback_query(F.data == "bank:account")
@router.callback_query(F.data == "bank:card")
async def cb_account(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    text = await bank_text(db, callback.from_user.id)
    if await send_sensitive_callback(callback, text, reply_markup=bank_kb()):
        return
    await callback.message.edit_text(text, reply_markup=bank_kb())
    await callback.answer()


@router.message(Command("pay"))
async def cmd_pay(message: Message, db: aiosqlite.Connection) -> None:
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.reply(err("формат команды: /pay @user сумма")) if message.chat.type in {"group", "supergroup"} else await message.answer(err("формат команды: /pay @user сумма"))
        return
    target = await m.find_user(db, parts[1])
    try:
        amount = float(parts[2].replace(",", "."))
    except ValueError:
        await message.reply(err("сумма указана неверно.")) if message.chat.type in {"group", "supergroup"} else await message.answer(err("сумма указана неверно."))
        return
    if not target:
        await message.reply(err("получатель не найден. Он должен хотя бы раз открыть бота.")) if message.chat.type in {"group", "supergroup"} else await message.answer(err("получатель не найден. Он должен хотя бы раз открыть бота."))
        return
    problem = await m.transfer_usd(db, message.from_user.id, target["telegram_id"], amount)
    await message.reply(err(problem) if problem else ok(f"перевод {money(amount)} выполнен.")) if message.chat.type in {"group", "supergroup"} else await message.answer(err(problem) if problem else ok(f"перевод {money(amount)} выполнен."))


@router.callback_query(F.data == "bank:transfer")
async def cb_transfer(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Переводы доступны только в личных сообщениях с ботом.", show_alert=True)
        return
    await state.set_state(PayForm.target)
    await callback.message.edit_text(f"{header('🔄 ПЕРЕВОД')}\nВведите @username или ID получателя.")
    await callback.answer()


@router.message(PayForm.target)
async def form_pay_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("получатель не найден."))
        return
    await state.update_data(target_id=target["telegram_id"])
    await state.set_state(PayForm.amount)
    await message.answer("Введите сумму перевода в USD.")


@router.message(PayForm.amount)
async def form_pay_amount(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("сумма указана неверно."))
        return
    data = await state.get_data()
    problem = await m.transfer_usd(db, message.from_user.id, int(data["target_id"]), amount)
    await state.clear()
    await message.answer(err(problem) if problem else ok(f"перевод {money(amount)} выполнен."))


@router.callback_query(F.data == "bank:deposits")
async def cb_deposits(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 10", (callback.from_user.id,))
    lines = [f"№{r['id']} · {money(r['amount'])} · {r['rate']}% · до {dt(r['ends_at'])} · {h(r['status'])}" for r in rows]
    text = f"{header('📈 ВКЛАДЫ')}\n" + ("\n".join(lines) if lines else "Вкладов пока нет.")
    markup = kb([[("3% на 7 дней", "deposit:7"), ("5% на 30 дней", "deposit:30")], [("8% на 90 дней", "deposit:90"), ("🏦 Назад", "bank:menu")]])
    if await send_sensitive_callback(callback, text, reply_markup=markup):
        return
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("deposit:"))
async def cb_deposit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Вклады доступны только в личных сообщениях с ботом.", show_alert=True)
        return
    await state.update_data(days=int(callback.data.split(":")[1]))
    await state.set_state(DepositForm.amount)
    await callback.message.edit_text(f"{header('📈 НОВЫЙ ВКЛАД')}\nВведите сумму вклада.")
    await callback.answer()


@router.message(DepositForm.amount)
async def form_deposit_amount(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("сумма указана неверно."))
        return
    days = int((await state.get_data())["days"])
    problem = await m.create_deposit(db, message.from_user.id, amount, days)
    await state.clear()
    await message.answer(err(problem) if problem else ok(f"вклад {money(amount)} открыт на {days} дней."))


@router.callback_query(F.data == "bank:loans")
async def cb_loans(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM loans WHERE user_id=? ORDER BY id DESC LIMIT 10", (callback.from_user.id,))
    lines = [f"№{r['id']} · остаток {money(r['remaining'])} · платёж {money(r['monthly_payment'])} · до {dt(r['due_date'])}" for r in rows]
    text = f"{header('💸 КРЕДИТЫ')}\n" + ("\n".join(lines) if lines else "Кредитов пока нет.")
    markup = kb([[("💸 Запросить кредит", "loan:new"), ("🏦 Назад", "bank:menu")]])
    if await send_sensitive_callback(callback, text, reply_markup=markup):
        return
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "loan:new")
async def cb_loan_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Кредиты доступны только в личных сообщениях с ботом.", show_alert=True)
        return
    await state.set_state(LoanForm.amount)
    await callback.message.edit_text(f"{header('💸 НОВЫЙ КРЕДИТ')}\nВведите сумму кредита.")
    await callback.answer()


@router.message(LoanForm.amount)
async def form_loan_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("сумма указана неверно."))
        return
    await state.update_data(amount=amount)
    await state.set_state(LoanForm.months)
    await message.answer("Введите срок в месяцах.")


@router.message(LoanForm.months)
async def form_loan_months(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    try:
        months = int(message.text or "")
    except ValueError:
        await message.answer(err("срок указан неверно."))
        return
    data = await state.get_data()
    problem = await m.create_loan(db, message.from_user.id, float(data["amount"]), months)
    await state.clear()
    await message.answer(err(problem) if problem else ok("кредит одобрен и зачислен на банковский счёт."))
