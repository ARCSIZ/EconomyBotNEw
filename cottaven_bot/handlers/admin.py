from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import GOV_POSITIONS, VEHICLES, settings
from database import models as m
from keyboards.main import admin_kb, kb
from utils.formatters import err, h, header, money, ok

router = Router()

TIMEOUT_SECONDS = 10


async def _timeout_clear(state: FSMContext, expected_state: str, prompt_id: int) -> None:
    await asyncio.sleep(TIMEOUT_SECONDS)
    if await state.get_state() != expected_state:
        return
    data = await state.get_data()
    if int(data.get("prompt_id", -1)) != prompt_id:
        return
    await state.clear()


def _is_reply_to_prompt(message: Message, prompt_id: int) -> bool:
    return bool(message.reply_to_message and message.reply_to_message.message_id == prompt_id)


class BalanceEdit(StatesGroup):
    target = State()
    field = State()
    amount = State()


class FineForm(StatesGroup):
    target = State()
    amount = State()
    reason = State()

class BanForm(StatesGroup):
    target = State()
    reason = State()


class UnbanForm(StatesGroup):
    target = State()


class VehicleGrant(StatesGroup):
    target = State()
    vehicle = State()


def is_admin(row) -> bool:
    return bool(row and row["role"] in {"admin", "owner"})

async def guard_admin_callback(callback: CallbackQuery, db: aiosqlite.Connection) -> bool:
    row = await m.get_user(db, callback.from_user.id)
    if not is_admin(row):
        await callback.answer("Нет доступа.", show_alert=True)
        return False
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Доступно только в ЛС.", show_alert=True)
        return False
    return True


async def guard_admin_message(message: Message, db: aiosqlite.Connection) -> bool:
    row = await m.get_user(db, message.from_user.id)
    if not is_admin(row):
        await message.answer(err("у вас нет доступа к панели администратора."))
        return False
    if message.chat.type != "private":
        await message.answer(err("панель администратора доступна только в личных сообщениях."))
        return False
    return True


@router.message(Command("admin"))
async def cmd_admin(message: Message, db: aiosqlite.Connection) -> None:
    row = await m.get_user(db, message.from_user.id)
    if message.chat.type != "private":
        await message.answer(err("панель администратора доступна только в личных сообщениях."))
        return
    if not is_admin(row):
        await message.answer(err("у вас нет доступа к панели администратора."))
        return
    await message.answer(f"{header('⚙️ ПАНЕЛЬ АДМИНИСТРАТОРА')}\nВыберите раздел.", reply_markup=admin_kb())


@router.callback_query(F.data == "admin:players")
async def cb_admin_players(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if not await guard_admin_callback(callback, db):
        return
    await callback.message.edit_text(
        f"{header('👤 ИГРОКИ')}\nВыберите действие.",
        reply_markup=kb([
            [("💰 Изменить баланс", "admin:balance"), ("⚖️ Выдать штраф", "admin:fine")],
            [("🚗 Выдать транспорт", "admin:vehicle"), ("🚫 Бан", "admin:ban")],
            [("✅ Разбан", "admin:unban"), ("⬅️ Назад", "admin:menu")],
        ]),
    )
    await callback.answer()

@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if not await guard_admin_callback(callback, db):
        return
    await callback.message.edit_text(f"{header('⚙️ ПАНЕЛЬ АДМИНИСТРАТОРА')}\nВыберите раздел.", reply_markup=admin_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:balance")
async def cb_balance(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BalanceEdit.target)
    await callback.message.edit_text("Ответьте на это сообщение: введите @username или ID игрока.\n\n⏳ Таймаут: 10 секунд.")
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, BalanceEdit.target.state, callback.message.message_id))
    await callback.answer()


@router.message(BalanceEdit.target)
async def form_balance_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден."))
        return
    await state.update_data(target_id=target["telegram_id"])
    await state.set_state(BalanceEdit.field)
    await message.answer("Выберите счёт.", reply_markup=kb([[("Наличные", "field:usd_cash"), ("Банк", "field:usd_bank")], [("BTC", "field:crypto_btc"), ("ETH", "field:crypto_eth"), ("USDT", "field:crypto_usdt")]]))


@router.callback_query(BalanceEdit.field, F.data.startswith("field:"))
async def cb_balance_field(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(field=callback.data.split(":")[1])
    await state.set_state(BalanceEdit.amount)
    await callback.message.edit_text("Введите изменение баланса. Можно отрицательное число.")
    await callback.answer()


@router.message(BalanceEdit.amount)
async def form_balance_amount(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("сумма указана неверно."))
        return
    data = await state.get_data()
    problem = await m.change_balance(db, int(data["target_id"]), amount, data["field"], "Изменение администратором", "transfer")
    await state.clear()
    await message.answer(err(problem) if problem else ok("баланс изменён."))


@router.callback_query(F.data == "admin:fine")
async def cb_admin_fine(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FineForm.target)
    await callback.message.edit_text("Ответьте на это сообщение: введите @username или ID игрока.\n\n⏳ Таймаут: 10 секунд.")
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, FineForm.target.state, callback.message.message_id))
    await callback.answer()


@router.message(FineForm.target)
async def form_fine_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден."))
        return
    await state.update_data(target_id=target["telegram_id"])
    await state.set_state(FineForm.amount)
    await message.answer("Введите сумму штрафа.")


@router.message(FineForm.amount)
async def form_fine_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer(err("сумма указана неверно."))
        return
    await state.update_data(amount=amount)
    await state.set_state(FineForm.reason)
    await message.answer("Введите причину штрафа.")


@router.message(FineForm.reason)
async def form_fine_reason(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    problem = await m.issue_fine(db, int(data["target_id"]), message.from_user.id, float(data["amount"]), message.text or "Нарушение")
    await state.clear()
    await message.answer(err(problem) if problem else ok("штраф выписан."))


@router.callback_query(F.data == "admin:ban")
async def cb_admin_ban(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_callback(callback, db):
        return
    await state.set_state(BanForm.target)
    await callback.message.edit_text("Ответьте на это сообщение: введите @username или ID игрока для бана.\n\n⏳ Таймаут: 10 секунд.")
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, BanForm.target.state, callback.message.message_id))
    await callback.answer()


@router.message(BanForm.target)
async def form_ban_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден."))
        return
    await state.update_data(target_id=target["telegram_id"])
    await state.set_state(BanForm.reason)
    await message.answer("Введите причину бана (или отправьте «-», чтобы пропустить).")


@router.message(BanForm.reason)
async def form_ban_reason(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    reason = (message.text or "").strip()
    reason = "" if reason == "-" else reason
    await db.execute("UPDATE users SET is_banned=1 WHERE telegram_id=?", (int(data["target_id"]),))
    if reason:
        await m.add_notification(db, int(data["target_id"]), "ban", f"Вы заблокированы администратором. Причина: {reason}")
    await db.commit()
    await state.clear()
    await message.answer(ok("игрок забанен."))


@router.callback_query(F.data == "admin:unban")
async def cb_admin_unban(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_callback(callback, db):
        return
    await state.set_state(UnbanForm.target)
    await callback.message.edit_text("Ответьте на это сообщение: введите @username или ID игрока для разбана.\n\n⏳ Таймаут: 10 секунд.")
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, UnbanForm.target.state, callback.message.message_id))
    await callback.answer()


@router.message(UnbanForm.target)
async def form_unban_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден."))
        return
    await db.execute("UPDATE users SET is_banned=0 WHERE telegram_id=?", (int(target["telegram_id"]),))
    await db.commit()
    await state.clear()
    await message.answer(ok("игрок разбанен."))


@router.callback_query(F.data == "admin:vehicle")
async def cb_admin_vehicle(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_callback(callback, db):
        return
    await state.set_state(VehicleGrant.target)
    await callback.message.edit_text("Ответьте на это сообщение: введите @username или ID игрока, которому выдать транспорт.\n\n⏳ Таймаут: 10 секунд.")
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, VehicleGrant.target.state, callback.message.message_id))
    await callback.answer()


@router.message(VehicleGrant.target)
async def form_vehicle_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден."))
        return
    await state.update_data(target_id=target["telegram_id"])
    await state.set_state(VehicleGrant.vehicle)
    labels = list(VEHICLES.keys())
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for idx, label in enumerate(labels):
        row.append((label, f"admin:vehicle:pick:{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("⬅️ Назад", "admin:players")])
    await message.answer("Выберите транспорт из списка.", reply_markup=kb(rows))


@router.callback_query(VehicleGrant.vehicle, F.data.startswith("admin:vehicle:pick:"))
async def cb_vehicle_pick(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    if not await guard_admin_callback(callback, db):
        await state.clear()
        return
    idx = int(callback.data.split(":")[3])
    labels = list(VEHICLES.keys())
    if idx < 0 or idx >= len(labels):
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    data = await state.get_data()
    label = labels[idx]
    brand, model, typ, price = VEHICLES[label]
    await db.execute(
        "INSERT INTO vehicles(owner_id, brand, model, plate_number, type, price) VALUES(?,?,?,?,?,?)",
        (int(data["target_id"]), brand, model, m.plate(), typ, price),
    )
    await m.add_notification(db, int(data["target_id"]), "vehicle", f"Вам выдан транспорт: {brand} {model}")
    await db.commit()
    await state.clear()
    await callback.message.edit_text(ok(f"транспорт выдан: {h(brand)} {h(model)}"))
    await callback.answer("Готово.")


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    users = await m.one(db, "SELECT COUNT(*) AS c FROM users")
    tx = await m.one(db, "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS s FROM transactions")
    await callback.message.edit_text(f"{header('📊 СТАТИСТИКА')}\nИгроков: {users['c']}\nТранзакций: {tx['c']}\nОборот: {money(tx['s'])}")
    await callback.answer()


@router.callback_query(F.data == "admin:system")
async def cb_admin_system(callback: CallbackQuery) -> None:
    backup = Path(str(settings.database_path) + ".backup")
    if settings.database_path.exists():
        shutil.copy2(settings.database_path, backup)
    await callback.message.edit_text(ok(f"резервная копия базы создана: {h(backup.name)}"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin_placeholder(callback: CallbackQuery) -> None:
    await callback.message.edit_text(f"{header('⚙️ АДМИН-ПАНЕЛЬ')}\nРаздел подготовлен. Используйте доступные кнопки управления игроками, статистики и системы.")
    await callback.answer()
