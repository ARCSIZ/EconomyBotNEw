from __future__ import annotations

import asyncio
import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database import models as m
from keyboards.main import kb
from utils.formatters import err, h, header, money, ok

router = Router()

FACTION_CREATE_CANCEL = "faction:create:cancel"
FACTION_CREATE_BACK = "faction:create:back"
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


class FactionCreate(StatesGroup):
    name = State()
    typ = State()
    description = State()


class FactionInvite(StatesGroup):
    target = State()

def _is_cancel_text(text: str | None) -> bool:
    t = (text or "").strip().lower()
    return t in {"/cancel", "cancel", "отмена", "❌ отмена", "стоп"}


async def _factions_text(db: aiosqlite.Connection) -> tuple[str, object]:
    rows = await m.all_rows(db, "SELECT f.*, u.username FROM factions f LEFT JOIN users u ON u.telegram_id=f.leader_id ORDER BY f.id")
    lines = [
        f"№{r['id']} · {h(r['logo_emoji'])} <b>{h(r['name'])}</b>\n"
        f"Тип: {h(r['type'])} · участников: {r['members_count']} · лидер: {('@' + r['username']) if r['username'] else '—'}"
        for r in rows
    ]
    text = f"{header('🏛 ФРАКЦИИ')}\n" + ("\n\n".join(lines) if lines else "Фракций пока нет.")
    markup = kb([[("➕ Создать фракцию", "faction:create")]])
    return text, markup


@router.message(Command("factions"))
async def cmd_factions(message: Message, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    text, markup = await _factions_text(db)
    await message.answer(text, reply_markup=markup)


@router.message(Command("faction"))
async def cmd_faction(message: Message, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    row = await m.one(db, "SELECT f.*, fm.rank, fm.salary FROM faction_members fm JOIN factions f ON f.id=fm.faction_id WHERE fm.user_id=?", (message.from_user.id,))
    if not row:
        await message.answer(f"{header('🏛 МОЯ ФРАКЦИЯ')}\nВы пока не состоите во фракции.", reply_markup=kb([[("📋 Все фракции", "factions:list")]]))
        return
    is_leader = row["leader_id"] == message.from_user.id
    buttons = [[("👥 Участники", f"faction:members:{row['id']}"), ("💰 Бюджет", f"faction:budget:{row['id']}")]]
    if is_leader:
        buttons.append([("➕ Пригласить", f"faction:invite:{row['id']}"), ("🗑 Удалить фракцию", f"faction:delete:{row['id']}")])
    buttons.append([("🚪 Покинуть", f"faction:leave:{row['id']}")])
    await message.answer(
        f"{header('🏛 МОЯ ФРАКЦИЯ')}\n"
        f"{h(row['logo_emoji'])} <b>{h(row['name'])}</b>\n"
        f"Ранг: {h(row['rank'])}\nЗарплата: {money(row['salary'])}\nБюджет: {money(row['budget'])}\n\n{h(row['description'])}",
        reply_markup=kb(buttons),
    )


@router.callback_query(F.data == "factions:list")
async def cb_factions(callback: CallbackQuery, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    text, markup = await _factions_text(db)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "faction:mine")
async def cb_faction_mine(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    fake = CallbackMessage(callback.message, callback.from_user.id)
    await cmd_faction(fake, db)
    await callback.answer()


class CallbackMessage:
    def __init__(self, message, user_id: int) -> None:
        self.message = message
        self.from_user = type("U", (), {"id": user_id})()
    async def answer(self, *args, **kwargs):
        return await self.message.edit_text(*args, **kwargs)


@router.callback_query(F.data.startswith("faction:members:"))
async def cb_faction_members(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    faction_id = int(callback.data.split(":")[2])
    rows = await m.all_rows(db, "SELECT fm.*, u.username, u.first_name FROM faction_members fm JOIN users u ON u.telegram_id=fm.user_id WHERE fm.faction_id=?", (faction_id,))
    lines = [f"{h(r['first_name'] or '@' + r['username'] if r['username'] else r['user_id'])} · {h(r['rank'])} · {money(r['salary'])}" for r in rows]
    await callback.message.edit_text(
        f"{header('👥 УЧАСТНИКИ')}\n" + ("\n".join(lines) if lines else "Участников пока нет."),
        reply_markup=kb([[("⬅️ Назад", "faction:mine")]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("faction:budget:"))
async def cb_faction_budget(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    row = await m.one(db, "SELECT * FROM factions WHERE id=?", (int(callback.data.split(":")[2]),))
    await callback.message.edit_text(
        f"{header('💰 БЮДЖЕТ ФРАКЦИИ')}\n{h(row['name'])}\nБюджет: <b>{money(row['budget'])}</b>",
        reply_markup=kb([[("⬅️ Назад", "faction:mine")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "faction:create")
async def cb_faction_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FactionCreate.name)
    await callback.message.edit_text(
        f"{header('➕ СОЗДАНИЕ ФРАКЦИИ')}\nСтоимость: $5,000.00\nВведите название фракции.",
        reply_markup=kb([[("⬅️ Назад", FACTION_CREATE_BACK), ("❌ Отмена", FACTION_CREATE_CANCEL)]]),
    )
    await callback.answer()


@router.callback_query(F.data.in_({FACTION_CREATE_CANCEL, FACTION_CREATE_BACK}))
async def cb_faction_create_cancel(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    await state.clear()
    text, markup = await _factions_text(db)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer("Отменено." if callback.data == FACTION_CREATE_CANCEL else "Назад.")


@router.message(FactionCreate.name)
async def form_faction_name(message: Message, state: FSMContext) -> None:
    if _is_cancel_text(message.text):
        await state.clear()
        await message.answer("Создание фракции отменено. Откройте /factions или /faction.")
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer(err("название не должно быть пустым."))
        return
    await state.update_data(name=name)
    await state.set_state(FactionCreate.typ)
    await message.answer("Введите тип фракции (например: «гос», «криминал», «бизнес», «иное»).\n\nМожно написать «Отмена».")


@router.message(FactionCreate.typ)
async def form_faction_type(message: Message, state: FSMContext) -> None:
    if _is_cancel_text(message.text):
        await state.clear()
        await message.answer("Создание фракции отменено. Откройте /factions или /faction.")
        return
    typ = (message.text or "").strip()
    if not typ:
        await message.answer(err("тип не должен быть пустым."))
        return
    await state.update_data(typ=typ)
    await state.set_state(FactionCreate.description)
    await message.answer("Введите описание фракции.\n\nМожно написать «Отмена».")


@router.message(FactionCreate.description)
async def form_faction_desc(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if _is_cancel_text(message.text):
        await state.clear()
        await message.answer("Создание фракции отменено. Откройте /factions или /faction.")
        return
    data = await state.get_data()
    user = await m.get_user(db, message.from_user.id)
    if not user:
        await state.clear()
        await message.answer(err("игрок не найден."))
        return
    if user["usd_bank"] < 5000:
        await state.clear()
        await message.answer(err("для создания фракции нужно $5,000.00 на банковском счёте."))
        return
    if user["faction_id"]:
        await state.clear()
        await message.answer(err("вы уже состоите во фракции. Сначала покиньте текущую."))
        return
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (5000, message.from_user.id))
    cur = await db.execute(
        "INSERT INTO factions(name, type, leader_id, description, members_count, budget, logo_emoji) VALUES(?,?,?,?,?,?,?)",
        (data["name"], data["typ"], message.from_user.id, (message.text or "").strip(), 1, 0, "🏛"),
    )
    faction_id = cur.lastrowid
    await db.execute("INSERT INTO faction_members(user_id, faction_id, rank, salary, role_id) VALUES(?,?,?,?,NULL)", (message.from_user.id, faction_id, "Лидер", 0))
    await m.ensure_default_roles_for_faction(db, faction_id, message.from_user.id)
    await db.execute("UPDATE users SET faction_id=? WHERE telegram_id=?", (faction_id, message.from_user.id))
    await m.log_tx(db, message.from_user.id, None, 5000, "USD", "purchase", "Создание фракции")
    await db.commit()
    await state.clear()
    await message.answer(ok("фракция создана. Используйте /faction чтобы открыть меню фракции."))


@router.callback_query(F.data.startswith("faction:invite:"))
async def cb_faction_invite(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление фракцией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    faction_id = int(callback.data.split(":")[2])
    faction = await m.one(db, "SELECT * FROM factions WHERE id=?", (faction_id,))
    if not faction:
        await callback.answer("Фракция не найдена.", show_alert=True)
        return
    if faction["leader_id"] != callback.from_user.id:
        await callback.answer("Приглашать может только лидер фракции.", show_alert=True)
        return
    await state.set_state(FactionInvite.target)
    await state.update_data(faction_id=faction_id)
    await callback.message.edit_text(
        f"{header('➕ ПРИГЛАШЕНИЕ В ФРАКЦИЮ')}\n{h(faction['logo_emoji'])} <b>{h(faction['name'])}</b>\nОтветьте на это сообщение: введите @username или ID игрока.\n\n⏳ Таймаут: 10 секунд.",
        reply_markup=kb([[("⬅️ Назад", "faction:mine")]]),
    )
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, FactionInvite.target.state, callback.message.message_id))
    await callback.answer()


@router.message(FactionInvite.target)
async def form_faction_invite_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    faction_id = int(data.get("faction_id", 0))
    faction = await m.one(db, "SELECT * FROM factions WHERE id=?", (faction_id,))
    if not faction:
        await state.clear()
        await message.answer(err("фракция не найдена."))
        return
    if faction["leader_id"] != message.from_user.id:
        await state.clear()
        await message.answer(err("приглашать может только лидер фракции."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден. Введите @username или ID."))
        return
    if target["faction_id"] == faction_id:
        await message.answer(err("игрок уже состоит в этой фракции."))
        return
    await m.ensure_default_roles_for_faction(db, faction_id, faction["leader_id"])
    role_id = await m.faction_member_role_id(db, faction_id)
    await m.create_org_invite(db, "faction", faction_id, int(target["telegram_id"]), message.from_user.id, role_id)
    await state.clear()
    await message.answer(ok("приглашение отправлено. Игрок получит уведомление и сможет принять его в боте."))


@router.callback_query(F.data.startswith("faction:delete:"))
async def cb_faction_delete(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление фракцией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    faction_id = int(callback.data.split(":")[2])
    faction = await m.one(db, "SELECT * FROM factions WHERE id=?", (faction_id,))
    if not faction:
        await callback.answer("Фракция не найдена.", show_alert=True)
        return
    if faction["leader_id"] != callback.from_user.id:
        await callback.answer("Удалять фракцию может только лидер.", show_alert=True)
        return
    await callback.message.edit_text(
        f"{header('🗑 УДАЛЕНИЕ ФРАКЦИИ')}\n"
        f"{h(faction['logo_emoji'])} <b>{h(faction['name'])}</b>\n\n"
        "Вы уверены, что хотите удалить фракцию? Участники будут отсоединены, приглашения обнулены.",
        reply_markup=kb([[("✅ Да, удалить", f"faction:delete:confirm:{faction_id}"), ("⬅️ Назад", "faction:mine")]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("faction:delete:confirm:"))
async def cb_faction_delete_confirm(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление фракцией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    faction_id = int(callback.data.split(":")[3])
    error = await m.safe_delete_faction(db, faction_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return
    await callback.message.edit_text(ok("фракция удалена."))
    await callback.answer("Готово.")


@router.callback_query(F.data.startswith("faction:leave:"))
async def cb_faction_leave(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    faction_id = int(callback.data.split(":")[2])
    row = await m.one(db, "SELECT * FROM faction_members WHERE user_id=? AND faction_id=?", (callback.from_user.id, faction_id))
    if not row:
        await callback.answer("Вы не состоите в этой фракции.", show_alert=True)
        return
    await db.execute("DELETE FROM faction_members WHERE user_id=? AND faction_id=?", (callback.from_user.id, faction_id))
    await db.execute("UPDATE users SET faction_id=NULL WHERE telegram_id=?", (callback.from_user.id,))
    await db.execute("UPDATE factions SET members_count=MAX(members_count-1,0) WHERE id=?", (faction_id,))
    await db.commit()
    await callback.message.edit_text(f"{header('🏛 МОЯ ФРАКЦИЯ')}\nВы покинули фракцию.", reply_markup=kb([[("📋 Все фракции", "factions:list")]]))
    await callback.answer("Готово.")
