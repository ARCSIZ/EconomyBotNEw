from __future__ import annotations

from aiogram.types import Message


SENSITIVE_COMMANDS = {"/crypto", "/fines", "/history", "/admin", "/settings"}


def is_sensitive_group_command(message: Message) -> bool:
    if message.chat.type not in {"group", "supergroup"} or not message.text:
        return False
    command = message.text.split(maxsplit=1)[0].split("@", 1)[0]
    return command in SENSITIVE_COMMANDS
