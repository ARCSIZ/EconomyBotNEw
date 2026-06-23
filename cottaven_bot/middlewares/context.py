from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from database.db import db as database
from database.models import ensure_user


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        conn = await database.connect()
        try:
            data["db"] = conn
            tg_user = None
            if isinstance(event, Message):
                tg_user = event.from_user
            elif isinstance(event, CallbackQuery):
                tg_user = event.from_user
            if tg_user:
                data["user_row"] = await ensure_user(conn, tg_user)
            return await handler(event, data)
        finally:
            await conn.close()
