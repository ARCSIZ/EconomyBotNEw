from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database import models as m
from handlers.start import send_sensitive_callback
from utils.formatters import dt, h, header, ok, err

router = Router()


async def notifications_text(db: aiosqlite.Connection, user_id: int) -> str:
    rows = await m.all_rows(db, "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
    return f"{header('🔔 УВЕДОМЛЕНИЯ')}\n" + ("\n\n".join(f"{dt(r['created_at'])} · {h(r['message'])}" for r in rows) if rows else "Новых уведомлений нет.")


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: aiosqlite.Connection) -> None:
    user = await m.get_user(db, message.from_user.id)
    state = "включены" if user["notifications_enabled"] else "выключены"
    await message.answer(f"{header('⚙️ НАСТРОЙКИ')}\nУведомления: <b>{state}</b>")


@router.callback_query(F.data == "settings:menu")
async def cb_settings(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        await callback.answer("Настройки доступны только в личных сообщениях с ботом.", show_alert=True)
        return
    user = await m.get_user(db, callback.from_user.id)
    new_value = 0 if user["notifications_enabled"] else 1
    await db.execute("UPDATE users SET notifications_enabled=? WHERE telegram_id=?", (new_value, callback.from_user.id))
    await db.commit()
    await callback.message.edit_text(ok("настройка уведомлений обновлена."))
    await callback.answer()


@router.callback_query(F.data == "notifications:menu")
async def cb_notifications(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    text = await notifications_text(db, callback.from_user.id)
    if await send_sensitive_callback(callback, text):
        return
    await callback.message.edit_text(text)
    await callback.answer()


def _invites_kb(invite_id: int) -> object:
    from keyboards.main import kb
    return kb([[("✅ Принять", f"invite:accept:{invite_id}"), ("❌ Отклонить", f"invite:decline:{invite_id}")], [("⬅️ Назад", "profile:menu")]])


@router.callback_query(F.data == "invites:menu")
async def cb_invites(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    invites = await m.list_org_invites_for_user(db, callback.from_user.id)
    lines: list[str] = []
    rows: list[list[tuple[str, str]]] = []
    for inv in invites[:10]:
        typ = "Компания" if inv["entity_type"] == "company" else "Фракция"
        lines.append(f"№{inv['id']} · {typ} <code>{inv['entity_id']}</code> · {dt(inv['created_at'])}")
        rows.append([("✅ Принять", f"invite:accept:{inv['id']}"), ("❌ Отклонить", f"invite:decline:{inv['id']}")])
    from keyboards.main import kb
    text = f"{header('📨 ПРИГЛАШЕНИЯ')}\n" + ("\n".join(lines) if lines else "У вас нет активных приглашений.")
    markup = kb(rows + [[("⬅️ Назад", "profile:menu")]])
    if await send_sensitive_callback(callback, text, reply_markup=markup):
        return
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("invite:decline:"))
async def cb_invite_decline(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    invite_id = int(callback.data.split(":")[2])
    inv = await m.get_org_invite(db, invite_id)
    if not inv or inv["invited_user_id"] != callback.from_user.id or inv["status"] != "pending":
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return
    await m.update_org_invite_status(db, invite_id, "declined")
    await callback.answer("Отклонено.")
    await cb_invites(callback, db)


@router.callback_query(F.data.startswith("invite:accept:"))
async def cb_invite_accept(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    invite_id = int(callback.data.split(":")[2])
    inv = await m.get_org_invite(db, invite_id)
    if not inv or inv["invited_user_id"] != callback.from_user.id or inv["status"] != "pending":
        await callback.answer("Приглашение не найдено.", show_alert=True)
        return
    if inv["entity_type"] == "company":
        problem = await m.accept_company_invite(db, inv)
    elif inv["entity_type"] == "faction":
        problem = await m.accept_faction_invite(db, inv)
    else:
        problem = "Неизвестный тип приглашения."
    if problem:
        await callback.answer(problem, show_alert=True)
        return
    await callback.answer("Принято.")
    await cb_invites(callback, db)


@router.callback_query(F.data == "achievements:menu")
async def cb_achievements(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    rows = await m.all_rows(db, "SELECT * FROM achievements WHERE user_id=? ORDER BY id DESC", (callback.from_user.id,))
    text = f"{header('⭐ ДОСТИЖЕНИЯ')}\n" + ("\n".join(f"• {h(r['achievement_key'])} · {dt(r['achieved_at'])}" for r in rows) if rows else "Достижений пока нет.")
    await callback.message.edit_text(text)
    await callback.answer()
