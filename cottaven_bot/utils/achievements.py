from __future__ import annotations

import aiosqlite


async def grant(db: aiosqlite.Connection, user_id: int, key: str) -> None:
    await db.execute("INSERT OR IGNORE INTO achievements(user_id, achievement_key) VALUES(?,?)", (user_id, key))
