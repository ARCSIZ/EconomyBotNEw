from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from config import E, SEP, THIN
from database import models as m
from keyboards.main import profile_kb
from middlewares.chat_type import is_sensitive_group_command
from utils.formatters import badge, dt, err, h, header, money

router = Router()


async def profile_text(db: aiosqlite.Connection, user_id: int) -> str:
    user = await m.get_user(db, user_id)
    faction = await m.one(db, "SELECT name FROM factions WHERE id=?", (user["faction_id"],)) if user and user["faction_id"] else None
    company = await m.one(db, "SELECT name FROM companies WHERE id=?", (user["company_id"],)) if user and user["company_id"] else None
    achievements = await m.one(db, "SELECT COUNT(*) AS c FROM achievements WHERE user_id=?", (user_id,))
    name = await m.user_name(user)
    gov = f"\n{h(user['gov_position'])}" if user and user["gov_position"] else ""
    return (
        f"{header('🏛 ЛИЧНЫЙ КАБИНЕТ')}\n"
        f"{badge(user['role'], user['gov_position'])} <b>{h(name)}</b> · {user['age']} лет{gov}\n"
        f"{SEP}\n"
        f"💵 Наличные: <b>{money(user['usd_cash'])}</b>\n"
        f"🏦 В банке: <b>{money(user['usd_bank'])}</b>\n"
        f"{THIN}\n"
        f"{E['btc']} {user['crypto_btc']:.8f} BTC\n"
        f"{E['eth']} {user['crypto_eth']:.6f} ETH\n"
        f"{E['usdt']} {user['crypto_usdt']:.2f} USDT\n"
        f"{SEP}\n"
        f"🏠 Фракция: {h(faction['name']) if faction else '—'}\n"
        f"🔥 Компания: {h(company['name']) if company else '—'}\n"
        f"⭐ Репутация: {user['reputation']} очков\n"
        f"🏆 Достижений: {achievements['c'] if achievements else 0}\n"
        f"{SEP}\n"
        f"📅 В системе с: {dt(user['registered_at'])}"
    )


@router.message(CommandStart())
@router.message(Command("profile"))
async def cmd_profile(message: Message, db: aiosqlite.Connection) -> None:
    text = await profile_text(db, message.from_user.id)
    await message.reply(text, reply_markup=profile_kb()) if message.chat.type in {"group", "supergroup"} else await message.answer(text, reply_markup=profile_kb())


@router.message(Command("balance"))
async def cmd_balance(message: Message, db: aiosqlite.Connection) -> None:
    user = await m.get_user(db, message.from_user.id)
    text = (
        f"{header('💰 БАЛАНС')}\n"
        f"💵 Наличные: <b>{money(user['usd_cash'])}</b>\n"
        f"🏦 Банк: <b>{money(user['usd_bank'])}</b>\n"
        f"{THIN}\n"
        f"{E['btc']} BTC: {user['crypto_btc']:.8f}\n"
        f"{E['eth']} ETH: {user['crypto_eth']:.6f}\n"
        f"{E['usdt']} USDT: {user['crypto_usdt']:.2f}"
    )
    await message.reply(text) if message.chat.type in {"group", "supergroup"} else await message.answer(text)


@router.message(Command("whois"))
async def cmd_whois(message: Message, db: aiosqlite.Connection) -> None:
    args = (message.text or "").split(maxsplit=1)
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = await m.get_user(db, message.reply_to_message.from_user.id)
    elif len(args) > 1:
        target = await m.find_user(db, args[1])
    if not target:
        await message.answer(err("игрок не найден. Используйте /whois @username или ответьте на сообщение игрока."))
        return
    name = await m.user_name(target)
    text = (
        f"{header('👤 ДОСЬЕ ИГРОКА')}\n"
        f"{badge(target['role'], target['gov_position'])} <b>{h(name)}</b>\n"
        f"{SEP}\n"
        f"ID: <code>{target['telegram_id']}</code>\n"
        f"Роль: {h(target['role'])}\n"
        f"Должность: {h(target['gov_position'] or '—')}\n"
        f"Репутация: {target['reputation']}\n"
        f"Регистрация: {dt(target['registered_at'])}"
    )
    await message.reply(text) if message.chat.type in {"group", "supergroup"} else await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        f"{header('📖 СПРАВКА')}\n"
        "<b>Основное</b>\n"
        "/start — личный кабинет\n/profile — профиль\n/balance — баланс\n"
        "/pay @user сумма — перевод USD\n/whois @user — информация об игроке\n"
        "/settings — настройки\n\n"
        "<b>Финансы</b>\n"
        "/bank — банк (вклады/кредиты/переводы)\n/crypto — крипто кошелёк\n/history — история баланса\n/fines — штрафы\n\n"
        "<b>Фракции и компании</b>\n"
        "/faction — моя фракция\n/factions — список фракций (есть кнопка «Создать фракцию»)\n"
        "/company — моя компания\n/companies — список компаний (есть кнопка «Создать компанию»)\n\n"
        "Если вы начали создание (фракции/компании) и передумали — нажмите кнопку «❌ Отмена»\n"
        "или просто перейдите в другое меню (создание больше не будет «спамить»).\n\n"
        "Владелец компании и лидер фракции могут приглашать людей через кнопки «➕ Пригласить»\n"
        "в меню /company и /faction. Приглашённые игроки получают уведомление от бота\n"
        "и могут принять приглашение прямо в личных сообщениях.\n\n"
        "<b>Имущество и активности</b>\n"
        "/businesses — мои бизнесы\n/market — рынок бизнесов\n/realestate — недвижимость\n/vehicles — транспорт\n"
        "/stocks — биржа (пока выводит список компаний/тикеров)\n"
        "/casino — казино\n/insurance — страховка\n/court — суд\n/top — топ игроков\n\n"
        "<b>Правительство</b>\n"
        "/gov — меню правительства\n/bill — законопроект\n/decree — указ\n/emergency — режим ЧП\n\n"
        "<b>Админка</b>\n"
        "/admin — панель администратора (в ЛС). Там можно: менять баланс, выписывать штрафы,\n"
        "банить/разбанивать игроков и выдавать транспорт."
    )
    await message.reply(text) if message.chat.type in {"group", "supergroup"} else await message.answer(text)


@router.message(F.new_chat_members)
async def welcome_group(message: Message) -> None:
    bot_id = message.bot.id
    if any(member.id == bot_id for member in message.new_chat_members):
        await message.answer(
            f"{header('🏛 COTTAVEN RP')}\n"
            "Бот экономики подключён к супергруппе.\n"
            f"{SEP}\n"
            "Команды профиля и баланса доступны здесь, приватные финансовые разделы будут отправляться в личные сообщения."
        )


async def send_sensitive_or_answer(message: Message, text: str, **kwargs) -> bool:
    if is_sensitive_group_command(message):
        try:
            await message.bot.send_message(message.from_user.id, text, **kwargs)
            await message.reply("📨 Информация отправлена вам в личные сообщения")
        except Exception:
            await message.reply(err("не удалось отправить личное сообщение. Сначала откройте диалог с ботом."))
        return True
    return False


async def send_sensitive_callback(callback: CallbackQuery, text: str, **kwargs) -> bool:
    if callback.message and callback.message.chat.type in {"group", "supergroup"}:
        try:
            await callback.bot.send_message(callback.from_user.id, text, **kwargs)
            await callback.answer("Информация отправлена вам в личные сообщения.", show_alert=True)
        except Exception:
            await callback.answer("Сначала откройте личный диалог с ботом.", show_alert=True)
        return True
    return False


@router.callback_query(F.data == "profile:menu")
async def cb_profile(callback: CallbackQuery, db: aiosqlite.Connection) -> None:
    await callback.message.edit_text(await profile_text(db, callback.from_user.id), reply_markup=profile_kb())
    await callback.answer()
