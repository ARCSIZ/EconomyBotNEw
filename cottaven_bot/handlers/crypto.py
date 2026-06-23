from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import E, SEP, settings
from database import models as m
from handlers.start import send_sensitive_callback, send_sensitive_or_answer
from keyboards.main import crypto_kb, kb
from utils.formatters import err, header, money, ok

router = Router()


class ExchangeForm(StatesGroup):
    asset = State()
    direction = State()
    amount = State()


class CryptoSendForm(StatesGroup):
    target = State()
    asset = State()
    amount = State()


async def crypto_text(db: aiosqlite.Connection, user_id: int) -> str:
    user = await m.get_user(db, user_id)
    return (
        f"{header('💎 КРИПТО КОШЕЛЁК')}\n"
        f"{E['btc']} Bitcoin: <b>{user['crypto_btc']:.8f} BTC</b> · {money(settings.crypto_rates['BTC'])}\n"
        f"{E['eth']} Ethereum: <b>{user['crypto_eth']:.6f} ETH</b> · {money(settings.crypto_rates['ETH'])}\n"
        f"{E['usdt']} USDT: <b>{user['crypto_usdt']:.2f} USDT</b> · {money(settings.crypto_rates['USDT'])}\n"
        f"{SEP}\n"
        f"🏦 Доступно в банке: <b>{money(user['usd_bank'])}</b>"
    )


@router.message(Command("crypto"))
async def cmd_crypto(message: Message, db: aiosqlite.Connection) -> None:
    text = await crypto_text(db, message.from_user.id)
    if await send_sensitive_or_answer(message, text, reply_markup=crypto_kb()):
        return
    await message.reply(text, reply_markup=crypto_kb()) if message.chat.type in {"group", "supergroup"} else await message.answer(text, reply_markup=crypto_kb())


@router.callback_query(F.data == "crypto:menu")
async def cb_crypto(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    text = await crypto_text(db, callback.from_user.id)
    if await send_sensitive_callback(callback, text, reply_markup=crypto_kb()):
        return
    await callback.message.edit_text(text, reply_markup=crypto_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("crypto:asset:"))
async def cb_asset(callback: CallbackQuery) -> None:
    asset = callback.data.split(":")[-1]
    await callback.answer(f"Курс {asset}: {money(settings.crypto_rates[asset])}", show_alert=True)


@router.callback_query(F.data == "crypto:exchange")
async def cb_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Обмен криптовалюты доступен только в личных сообщениях с ботом.", show_alert=True)
        return
    await state.set_state(ExchangeForm.asset)
    await callback.message.edit_text(
        f"{header('🔄 ОБМЕН КРИПТОВАЛЮТЫ')}\nВыберите валюту.",
        reply_markup=kb([[("BTC", "exasset:BTC"), ("ETH", "exasset:ETH"), ("USDT", "exasset:USDT")]]),
    )
    await callback.answer()


@router.callback_query(ExchangeForm.asset, F.data.startswith("exasset:"))
async def cb_exchange_asset(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(asset=callback.data.split(":")[1])
    await state.set_state(ExchangeForm.direction)
    await callback.message.edit_text("Выберите операцию.", reply_markup=kb([[("Купить", "exdir:buy"), ("Продать", "exdir:sell")]]))
    await callback.answer()


@router.callback_query(ExchangeForm.direction, F.data.startswith("exdir:"))
async def cb_exchange_dir(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(direction=callback.data.split(":")[1])
    await state.set_state(ExchangeForm.amount)
    await callback.message.edit_text("Введите количество криптовалюты.")
    await callback.answer()


@router.message(ExchangeForm.amount)
async def form_exchange_amount(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("количество указано неверно."))
        return
    data = await state.get_data()
    problem = await m.exchange_crypto(db, message.from_user.id, data["asset"], amount, data["direction"])
    await state.clear()
    await message.answer(err(problem) if problem else ok("обмен выполнен."))


@router.callback_query(F.data == "crypto:send")
async def cb_send_crypto(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Отправка криптовалюты доступна только в личных сообщениях с ботом.", show_alert=True)
        return
    await state.set_state(CryptoSendForm.target)
    await callback.message.edit_text(f"{header('📤 ОТПРАВКА КРИПТО')}\nВведите @username или ID получателя.")
    await callback.answer()


@router.message(CryptoSendForm.target)
async def form_crypto_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("получатель не найден."))
        return
    await state.update_data(target_id=target["telegram_id"])
    await state.set_state(CryptoSendForm.asset)
    await message.answer("Введите валюту: BTC, ETH или USDT.")


@router.message(CryptoSendForm.asset)
async def form_crypto_asset(message: Message, state: FSMContext) -> None:
    asset = (message.text or "").upper()
    if asset not in {"BTC", "ETH", "USDT"}:
        await message.answer(err("доступны только BTC, ETH или USDT."))
        return
    await state.update_data(asset=asset)
    await state.set_state(CryptoSendForm.amount)
    await message.answer("Введите количество.")


@router.message(CryptoSendForm.amount)
async def form_crypto_amount(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("количество указано неверно."))
        return
    data = await state.get_data()
    asset = data["asset"]
    field = f"crypto_{asset.lower()}"
    sender = await m.get_user(db, message.from_user.id)
    if sender[field] < amount or amount <= 0:
        await message.answer(err("недостаточно криптовалюты."))
        return
    await db.execute(f"UPDATE users SET {field}={field}-? WHERE telegram_id=?", (amount, message.from_user.id))
    await db.execute(f"UPDATE users SET {field}={field}+? WHERE telegram_id=?", (amount, int(data["target_id"])))
    await m.log_tx(db, message.from_user.id, int(data["target_id"]), amount, asset, "transfer", f"Перевод {asset}")
    await db.commit()
    await state.clear()
    await message.answer(ok(f"перевод {amount:g} {asset} выполнен."))
