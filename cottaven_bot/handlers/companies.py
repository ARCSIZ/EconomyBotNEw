from __future__ import annotations

import asyncio
import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database import models as m
from keyboards.main import kb, company_manage_kb
from utils.formatters import err, h, header, money, ok

router = Router()

COMPANY_CREATE_CANCEL = "company:create:cancel"
COMPANY_CREATE_BACK = "company:create:back"
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


class CompanyCreate(StatesGroup):
    name = State()
    description = State()
    typ = State()


class CompanyInvite(StatesGroup):
    target = State()


@router.callback_query(F.data.startswith("company:invite:"))
async def cb_company_invite(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление компанией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    company_id = int(callback.data.split(":")[2])
    company = await m.one(db, "SELECT * FROM companies WHERE id=?", (company_id,))
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    if company["owner_id"] != callback.from_user.id:
        await callback.answer("Приглашать может только владелец компании.", show_alert=True)
        return
    await state.set_state(CompanyInvite.target)
    await state.update_data(company_id=company_id)
    await callback.message.edit_text(
        f"{header('➕ ПРИГЛАШЕНИЕ В КОМПАНИЮ')}\n<b>{h(company['name'])}</b>\nОтветьте на это сообщение: введите @username или ID игрока.\n\n⏳ Таймаут: 10 секунд.",
        reply_markup=kb([[("⬅️ Назад", f"company:manage:{company_id}")]]),
    )
    await state.update_data(prompt_id=callback.message.message_id)
    asyncio.create_task(_timeout_clear(state, CompanyInvite.target.state, callback.message.message_id))
    await callback.answer()


@router.message(CompanyInvite.target)
async def form_company_invite_target(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    prompt_id = int(data.get("prompt_id", 0))
    if prompt_id and not _is_reply_to_prompt(message, prompt_id):
        await message.answer(err("введите данные ответом (Reply) на сообщение бота, где он это запросил."))
        return
    company_id = int(data.get("company_id", 0))
    company = await m.one(db, "SELECT * FROM companies WHERE id=?", (company_id,))
    if not company:
        await state.clear()
        await message.answer(err("компания не найдена."))
        return
    if company["owner_id"] != message.from_user.id:
        await state.clear()
        await message.answer(err("приглашать может только владелец компании."))
        return
    target = await m.find_user(db, message.text or "")
    if not target:
        await message.answer(err("игрок не найден. Введите @username или ID."))
        return
    if target["company_id"] == company_id:
        await message.answer(err("игрок уже состоит в этой компании."))
        return
    await m.ensure_default_roles_for_company(db, company_id, company["owner_id"])
    role_id = await m.company_member_role_id(db, company_id)
    await m.create_org_invite(db, "company", company_id, int(target["telegram_id"]), message.from_user.id, role_id)
    await state.clear()
    await message.answer(ok("приглашение отправлено. Игрок получит уведомление и сможет принять его в боте."))


@router.message(Command("companies"))
async def cmd_companies(message: Message, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    rows = await m.all_rows(db, "SELECT c.*, u.username FROM companies c LEFT JOIN users u ON u.telegram_id=c.owner_id ORDER BY c.id")
    lines = [f"№{r['id']} · <b>{h(r['name'])}</b>\nТип: {h(r['type'])} · бюджет: {money(r['budget'])} · владелец: {('@' + r['username']) if r['username'] else '—'}" for r in rows]
    await message.answer(f"{header('🏢 КОМПАНИИ')}\n" + ("\n\n".join(lines) if lines else "Компаний пока нет."), reply_markup=kb([[("➕ Создать компанию", "company:create")]]))


@router.callback_query(F.data == "companies:list")
async def cb_companies_list(callback: CallbackQuery, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    rows = await m.all_rows(db, "SELECT c.*, u.username FROM companies c LEFT JOIN users u ON u.telegram_id=c.owner_id ORDER BY c.id")
    lines = [f"№{r['id']} · <b>{h(r['name'])}</b>\nТип: {h(r['type'])} · бюджет: {money(r['budget'])} · владелец: {('@' + r['username']) if r['username'] else '—'}" for r in rows]
    await callback.message.edit_text(
        f"{header('🏢 КОМПАНИИ')}\n" + ("\n\n".join(lines) if lines else "Компаний пока нет."),
        reply_markup=kb([[("➕ Создать компанию", "company:create")]]),
    )
    await callback.answer()


@router.message(Command("company"))
async def cmd_company(message: Message, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    row = await m.one(db, "SELECT * FROM companies WHERE owner_id=? OR id=(SELECT company_id FROM company_employees WHERE user_id=? LIMIT 1)", (message.from_user.id, message.from_user.id))
    if not row:
        await message.answer(f"{header('🔥 МОЯ КОМПАНИЯ')}\nУ вас пока нет компании.", reply_markup=kb([[("➕ Создать компанию", "company:create"), ("🏢 Все компании", "companies:list")]]))
        return
    await message.answer(
        f"{header('🔥 МОЯ КОМПАНИЯ')}\n<b>{h(row['name'])}</b>\nТип: {h(row['type'])}\nБюджет: {money(row['budget'])}\n\n{h(row['description'])}",
        reply_markup=kb([
            [("👥 Сотрудники", f"company:employees:{row['id']}"), ("💰 Бюджет", f"company:budget:{row['id']}")],
            [("📊 Акции", f"company:stocks:{row['id']}"), ("⚙️ Управление", f"company:manage:{row['id']}")],
        ]),
    )


@router.callback_query(F.data == "company:mine")
async def cb_company_mine(callback: CallbackQuery, db: aiosqlite.Connection, state: FSMContext) -> None:
    await state.clear()
    row = await m.one(db, "SELECT * FROM companies WHERE owner_id=? OR id=(SELECT company_id FROM company_employees WHERE user_id=? LIMIT 1)", (callback.from_user.id, callback.from_user.id))
    if not row:
        await callback.message.edit_text(f"{header('🔥 МОЯ КОМПАНИЯ')}\nУ вас пока нет компании.", reply_markup=kb([[("➕ Создать компанию", "company:create")]]))
    else:
        await callback.message.edit_text(
            f"{header('🔥 МОЯ КОМПАНИЯ')}\n<b>{h(row['name'])}</b>\nТип: {h(row['type'])}\nБюджет: {money(row['budget'])}\n\n{h(row['description'])}",
            reply_markup=kb([
                [("👥 Сотрудники", f"company:employees:{row['id']}"), ("💰 Бюджет", f"company:budget:{row['id']}")],
                [("📊 Акции", f"company:stocks:{row['id']}"), ("⚙️ Управление", f"company:manage:{row['id']}")],
            ]),
        )
    await callback.answer()

def _is_cancel_text(text: str | None) -> bool:
    t = (text or "").strip().lower()
    return t in {"/cancel", "cancel", "отмена", "❌ отмена", "стоп"}


@router.callback_query(F.data == "company:create")
async def cb_company_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CompanyCreate.name)
    await callback.message.edit_text(
        f"{header('➕ СОЗДАНИЕ КОМПАНИИ')}\nСтоимость: $10,000.00\nВведите название компании.",
        reply_markup=kb([[("⬅️ Назад", COMPANY_CREATE_BACK), ("❌ Отмена", COMPANY_CREATE_CANCEL)]]),
    )
    await callback.answer()

@router.callback_query(F.data.in_({COMPANY_CREATE_CANCEL, COMPANY_CREATE_BACK}))
async def cb_company_create_cancel(callback: CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    await state.clear()
    # Возвращаем пользователя в список компаний (без "залипания" формы)
    rows = await m.all_rows(db, "SELECT c.*, u.username FROM companies c LEFT JOIN users u ON u.telegram_id=c.owner_id ORDER BY c.id")
    lines = [f"№{r['id']} · <b>{h(r['name'])}</b>\nТип: {h(r['type'])} · бюджет: {money(r['budget'])} · владелец: {('@' + r['username']) if r['username'] else '—'}" for r in rows]
    await callback.message.edit_text(
        f"{header('🏢 КОМПАНИИ')}\n" + ("\n\n".join(lines) if lines else "Компаний пока нет."),
        reply_markup=kb([[("➕ Создать компанию", "company:create")]]),
    )
    await callback.answer("Отменено." if callback.data == COMPANY_CREATE_CANCEL else "Назад.")


@router.message(CompanyCreate.name)
async def form_company_name(message: Message, state: FSMContext) -> None:
    if _is_cancel_text(message.text):
        await state.clear()
        await message.answer("Создание компании отменено. Откройте /companies или /company.")
        return
    if not (message.text or "").strip():
        await message.answer(err("название не должно быть пустым."))
        return
    await state.update_data(name=message.text)
    await state.set_state(CompanyCreate.description)
    await message.answer("Введите описание компании.\n\nМожно написать «Отмена» чтобы прекратить создание.")


@router.message(CompanyCreate.description)
async def form_company_desc(message: Message, state: FSMContext) -> None:
    if _is_cancel_text(message.text):
        await state.clear()
        await message.answer("Создание компании отменено. Откройте /companies или /company.")
        return
    await state.update_data(description=message.text)
    await state.set_state(CompanyCreate.typ)
    await message.answer("Введите тип деятельности (например: «IT», «Полиция», «Банк», «Казино»).\n\nМожно написать «Отмена».")


@router.message(CompanyCreate.typ)
async def form_company_type(message: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    if _is_cancel_text(message.text):
        await state.clear()
        await message.answer("Создание компании отменено. Откройте /companies или /company.")
        return
    typ = (message.text or "").strip()
    if not typ:
        await message.answer(err("тип деятельности не должен быть пустым."))
        return
    await state.update_data(typ=typ)
    data = await state.get_data()
    user = await m.get_user(db, message.from_user.id)
    if user["usd_bank"] < 10000:
        await state.clear()
        await message.answer(err("для создания компании нужно $10,000.00 на банковском счёте."))
        return
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (10000, message.from_user.id))
    cur = await db.execute(
        "INSERT INTO companies(name, type, owner_id, description) VALUES(?,?,?,?)",
        (data["name"], data["typ"], message.from_user.id, data["description"]),
    )
    company_id = cur.lastrowid
    await db.execute("UPDATE users SET company_id=? WHERE telegram_id=?", (company_id, message.from_user.id))
    await db.execute("INSERT INTO company_employees(user_id, company_id, role, salary, role_id) VALUES(?,?,?,?,NULL)", (message.from_user.id, company_id, "CEO", 0))
    await m.ensure_default_roles_for_company(db, company_id, message.from_user.id)
    await m.log_tx(db, message.from_user.id, None, 10000, "USD", "purchase", "Создание компании")
    await db.commit()
    await state.clear()
    await message.answer(ok("компания создана."))


@router.callback_query(F.data.startswith("company:manage:"))
async def cb_company_manage(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление компанией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    company_id = int(callback.data.split(":")[2])
    row = await m.one(db, "SELECT * FROM companies WHERE id=?", (company_id,))
    if not row or row["owner_id"] != callback.from_user.id:
        await callback.answer("Управление доступно только владельцу компании.", show_alert=True)
        return
    await m.ensure_default_roles_for_company(db, company_id, callback.from_user.id)
    await callback.message.edit_text(
        f"{header('⚙️ УПРАВЛЕНИЕ КОМПАНИЕЙ')}\n<b>{h(row['name'])}</b>\nВы владелец этой компании. Здесь можно приглашать сотрудников, настраивать роли и удалить компанию.",
        reply_markup=company_manage_kb(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("company:employees:"))
@router.callback_query(F.data.startswith("company:budget:"))
@router.callback_query(F.data.startswith("company:stocks:"))
@router.callback_query(F.data.startswith("company:members:"))
@router.callback_query(F.data.startswith("company:roles:"))
@router.callback_query(F.data.startswith("company:edit:"))
async def cb_company_restrict_private(callback: CallbackQuery) -> None:
    # Чтобы в группах никто не мог «тыкать чужие панели»
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Раздел доступен только в личных сообщениях с ботом.", show_alert=True)
        return
    await callback.answer("Раздел в разработке.", show_alert=True)


@router.callback_query(F.data.startswith("company:delete:"))
async def cb_company_delete(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление компанией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    company_id = int(callback.data.split(":")[2])
    row = await m.one(db, "SELECT * FROM companies WHERE id=?", (company_id,))
    if not row:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    if row["owner_id"] != callback.from_user.id:
        await callback.answer("Удалять компанию может только владелец.", show_alert=True)
        return
    await callback.message.edit_text(
        f"{header('🗑 УДАЛЕНИЕ КОМПАНИИ')}\n"
        f"<b>{h(row['name'])}</b>\n\n"
        "Вы уверены, что хотите удалить компанию? Все сотрудники будут отсоединены, акции и приглашения обнулены.",
        reply_markup=kb([[("✅ Да, удалить", f"company:delete:confirm:{company_id}"), ("⬅️ Назад", f"company:manage:{company_id}")]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("company:delete:confirm:"))
async def cb_company_delete_confirm(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type != "private":
        await callback.answer("Управление компанией доступно только в личных сообщениях с ботом.", show_alert=True)
        return
    company_id = int(callback.data.split(":")[3])
    error = await m.safe_delete_company(db, company_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return
    await callback.message.edit_text(ok("компания удалена."))
    await callback.answer("Готово.")
