from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from loguru import logger

from config import settings
from database.db import Database, db
from handlers import admin, bank, businesses, casino, companies, court, crypto, factions, fines, government, history, insurance, notifications, realestate, start, stocks, supergroup, top, vehicles
from middlewares.antispam import AntiSpamMiddleware
from middlewares.ban_check import BanCheckMiddleware
from middlewares.context import DatabaseMiddleware
from schedulers.tasks import setup_scheduler


def _configure_windows_utf8_console() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(AntiSpamMiddleware())
    for router in (
        start.router,
        bank.router,
        crypto.router,
        fines.router,
        history.router,
        factions.router,
        businesses.router,
        companies.router,
        realestate.router,
        vehicles.router,
        stocks.router,
        casino.router,
        insurance.router,
        court.router,
        government.router,
        admin.router,
        notifications.router,
        top.router,
        supergroup.router,
    ):
        dp.include_router(router)
    return dp


async def set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="личный кабинет"),
        BotCommand(command="profile", description="профиль"),
        BotCommand(command="balance", description="баланс"),
        BotCommand(command="pay", description="перевод USD"),
        BotCommand(command="bank", description="банк"),
        BotCommand(command="crypto", description="крипто кошелёк"),
        BotCommand(command="fines", description="штрафы"),
        BotCommand(command="history", description="история баланса"),
        BotCommand(command="faction", description="моя фракция"),
        BotCommand(command="factions", description="все фракции"),
        BotCommand(command="company", description="моя компания"),
        BotCommand(command="companies", description="все компании"),
        BotCommand(command="businesses", description="мои бизнесы"),
        BotCommand(command="market", description="рынок бизнесов"),
        BotCommand(command="realestate", description="недвижимость"),
        BotCommand(command="vehicles", description="транспорт"),
        BotCommand(command="stocks", description="биржа"),
        BotCommand(command="casino", description="казино"),
        BotCommand(command="insurance", description="страховка"),
        BotCommand(command="court", description="суд"),
        BotCommand(command="top", description="топ игроков"),
        BotCommand(command="gov", description="правительство"),
        BotCommand(command="bill", description="законопроект (гос)"),
        BotCommand(command="decree", description="указ (гос)"),
        BotCommand(command="emergency", description="ЧП (гос)"),
        BotCommand(command="whois", description="информация об игроке"),
        BotCommand(command="settings", description="настройки"),
        BotCommand(command="help", description="помощь"),
        BotCommand(command="admin", description="панель администратора"),
    ]
    await bot.set_my_commands(commands)


async def dry_run() -> None:
    build_dispatcher()
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db = Database(Path(temp_dir) / "dry_run.sqlite3")
        await test_db.init()
    logger.info("Сухой запуск успешен: импорты, роутеры и схема базы данных корректны.")


async def main() -> None:
    _configure_windows_utf8_console()
    if "--dry-run" in sys.argv:
        await dry_run()
        return
    if not settings.bot_token:
        raise RuntimeError("Не указан BOT_TOKEN в файле .env")
    await db.init()
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = setup_scheduler(bot)
    await set_bot_commands(bot)
    logger.info("COTTAVEN RP бот запущен")
    try:
        await build_dispatcher().start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
