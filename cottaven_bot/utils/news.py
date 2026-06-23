from __future__ import annotations

from aiogram import Bot


async def publish(bot: Bot, channel_id: int | None, title: str, content: str) -> None:
    if channel_id:
        await bot.send_message(channel_id, f"📰 <b>{title}</b>\n{content}")
