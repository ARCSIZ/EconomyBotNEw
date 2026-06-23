from __future__ import annotations

from pathlib import Path

import aiosqlite
from loguru import logger

from config import settings


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    age INTEGER DEFAULT 18,
    usd_cash REAL DEFAULT 5000,
    usd_bank REAL DEFAULT 12000,
    crypto_btc REAL DEFAULT 0,
    crypto_eth REAL DEFAULT 0,
    crypto_usdt REAL DEFAULT 250,
    role TEXT DEFAULT 'user',
    gov_position TEXT,
    faction_id INTEGER,
    company_id INTEGER,
    reputation INTEGER DEFAULT 0,
    registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_banned INTEGER DEFAULT 0,
    notifications_enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS bank_cards (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, card_number TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, rate REAL, duration_days INTEGER, started_at TEXT DEFAULT CURRENT_TIMESTAMP, ends_at TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS loans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, rate REAL, monthly_payment REAL, remaining REAL, due_date TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS factions (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, leader_id INTEGER, description TEXT, members_count INTEGER DEFAULT 0, budget REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, logo_emoji TEXT DEFAULT '🏛');
CREATE TABLE IF NOT EXISTS faction_members (user_id INTEGER, faction_id INTEGER, rank TEXT DEFAULT 'Участник', salary REAL DEFAULT 0, joined_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, faction_id));
CREATE TABLE IF NOT EXISTS faction_ranks (id INTEGER PRIMARY KEY AUTOINCREMENT, faction_id INTEGER, rank_name TEXT, salary REAL, permissions TEXT);
CREATE TABLE IF NOT EXISTS businesses (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, owner_id INTEGER, company_id INTEGER, income_per_hour REAL, price REAL, level INTEGER DEFAULT 1, last_collected_at TEXT DEFAULT CURRENT_TIMESTAMP, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, owner_id INTEGER, budget REAL DEFAULT 0, description TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS company_employees (user_id INTEGER, company_id INTEGER, role TEXT, salary REAL DEFAULT 0, joined_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, company_id));
CREATE TABLE IF NOT EXISTS real_estate (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, district TEXT, owner_id INTEGER, price REAL, rent_price REAL, is_rented INTEGER DEFAULT 0, renter_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS real_estate_mortgages (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER, user_id INTEGER, total_amount REAL, monthly_payment REAL, remaining REAL, due_date TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS vehicles (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, brand TEXT, model TEXT, plate_number TEXT, type TEXT, price REAL DEFAULT 0, insurance_until TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS stock_market (id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER, ticker TEXT, price_per_share REAL, total_shares INTEGER, available_shares INTEGER, last_updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS stock_holdings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, company_id INTEGER, shares_count INTEGER, bought_at_price REAL);
CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, from_user INTEGER, to_user INTEGER, amount REAL, currency TEXT, type TEXT, description TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS fines (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, issued_by INTEGER, amount REAL, reason TEXT, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS balance_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, change_amount REAL, currency TEXT, reason TEXT, balance_after REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS invites (id INTEGER PRIMARY KEY AUTOINCREMENT, from_user INTEGER, to_entity_type TEXT, to_entity_id INTEGER, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS achievements (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, achievement_key TEXT, achieved_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, achievement_key));
CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS laws (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, text TEXT, proposed_by INTEGER, status TEXT DEFAULT 'proposed', signed_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS court_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, plaintiff_id INTEGER, defendant_id INTEGER, description TEXT, verdict TEXT, judge_id INTEGER, status TEXT DEFAULT 'open', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS government_treasury (id INTEGER PRIMARY KEY CHECK(id=1), balance REAL DEFAULT 1000000, last_updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tax_rates (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT UNIQUE, rate_percent REAL, set_by INTEGER, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS insurance_policies (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, object_id INTEGER, premium REAL, coverage REAL, expires_at TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS news_log (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, title TEXT, content TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS casino_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, game_type TEXT, bet REAL, result TEXT, payout REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS company_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    permissions_json TEXT NOT NULL,
    is_owner_role INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS faction_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faction_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    permissions_json TEXT NOT NULL,
    is_owner_role INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS org_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    invited_user_id INTEGER NOT NULL,
    invited_by_user_id INTEGER NOT NULL,
    role_id INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT
);
"""


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or settings.database_path)

    async def connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = await self.connect()
        try:
            await db.executescript(SCHEMA)
            
            # === Безопасное добавление новых колонок ===
            await self._add_column_if_not_exists(db, "company_employees", "role_id", "INTEGER")
            await self._add_column_if_not_exists(db, "faction_members", "role_id", "INTEGER")
            
            await seed_defaults(db)
            await db.commit()
            logger.info("База данных успешно инициализирована: {}", self.path)
            
        finally:
            await db.close()

    async def _add_column_if_not_exists(
        self, db: aiosqlite.Connection, table: str, column: str, column_type: str
    ) -> None:
        """Безопасно добавляет колонку, если она ещё не существует"""
        try:
            await db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {column_type};')
            logger.info(f"Добавлена колонка {column} в таблицу {table}")
        except aiosqlite.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                # Колонка уже существует — это нормально
                pass
            else:
                logger.error(f"Ошибка при добавлении колонки {column} в {table}: {e}")
                raise


async def seed_defaults(db: aiosqlite.Connection) -> None:
    await db.execute("INSERT OR IGNORE INTO government_treasury(id, balance) VALUES(1, 1000000)")
    for kind, rate in (("income", 7), ("business", 5), ("property", 1), ("vehicle", 1)):
        await db.execute(
            "INSERT OR IGNORE INTO tax_rates(type, rate_percent, set_by) VALUES(?, ?, 0)",
            (kind, rate),
        )
    cur = await db.execute("SELECT id FROM factions WHERE type='government' ORDER BY id LIMIT 1")
    if not await cur.fetchone():
        await db.execute(
            "INSERT INTO factions(name, type, description, budget, logo_emoji) VALUES(?,?,?,?,?)",
            (
                "Правительство США — Лос-Анджелес",
                "government",
                "Официальный орган государственной власти штата Калифорния",
                1000000,
                "🏛",
            ),
        )


db = Database()