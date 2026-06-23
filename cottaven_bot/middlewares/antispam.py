from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, cooldown: float = 3.0) -> None:
        self.cooldown = cooldown
        self.seen: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.chat.type not in {"group", "supergroup"}:
            return await handler(event, data)
        if not event.text or not event.text.startswith("/"):
            return await handler(event, data)
        command = event.text.split(maxsplit=1)[0].split("@", 1)[0]
        key = (event.from_user.id if event.from_user else 0, command)
        current = time.monotonic()
        previous = self.seen.get(key, 0)
        if current - previous < self.cooldown:
            await event.reply("⏳ Подождите несколько секунд перед повторной командой.")
            return None
        self.seen[key] = current
        return await handler(event, data)
