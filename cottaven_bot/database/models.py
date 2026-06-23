from __future__ import annotations

import json
import random
import string
from datetime import datetime, timedelta
from typing import Any

import aiosqlite
from aiogram.types import User

from config import BUSINESS_TYPES, REAL_ESTATE, VEHICLES, settings


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def card_number() -> str:
    digits = "4" + "".join(random.choice(string.digits) for _ in range(15))
    return " ".join(digits[i:i + 4] for i in range(0, 16, 4))


def plate() -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return f"{random.choice(letters)}{random.choice(letters)}{random.randint(1000, 9999)}"


async def one(db: aiosqlite.Connection, query: str, args: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
    cur = await db.execute(query, args)
    return await cur.fetchone()


async def all_rows(db: aiosqlite.Connection, query: str, args: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
    cur = await db.execute(query, args)
    return list(await cur.fetchall())


async def ensure_user(db: aiosqlite.Connection, user: User | Any) -> aiosqlite.Row:
    admin_role = "admin" if user.id in settings.admin_ids else "user"
    await db.execute(
        """
        INSERT INTO users(telegram_id, username, first_name, last_name, role)
        VALUES(?,?,?,?,?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name
        """,
        (user.id, user.username, user.first_name, user.last_name, admin_role),
    )
    exists = await one(db, "SELECT id FROM bank_cards WHERE user_id=?", (user.id,))
    if not exists:
        await db.execute("INSERT INTO bank_cards(user_id, card_number) VALUES(?,?)", (user.id, card_number()))
    await db.commit()
    return await get_user(db, user.id)  # type: ignore[return-value]


async def get_user(db: aiosqlite.Connection, user_id: int) -> aiosqlite.Row | None:
    return await one(db, "SELECT * FROM users WHERE telegram_id=?", (user_id,))


async def find_user(db: aiosqlite.Connection, value: str) -> aiosqlite.Row | None:
    value = value.strip()
    if value.startswith("@"):
        return await one(db, "SELECT * FROM users WHERE lower(username)=lower(?)", (value[1:],))
    if value.isdigit():
        return await get_user(db, int(value))
    return await one(db, "SELECT * FROM users WHERE lower(username)=lower(?)", (value,))


async def user_name(row: aiosqlite.Row | None) -> str:
    if not row:
        return "Неизвестный игрок"
    full = " ".join(x for x in (row["first_name"], row["last_name"]) if x)
    return full or (f"@{row['username']}" if row["username"] else str(row["telegram_id"]))


async def transfer_usd(db: aiosqlite.Connection, from_id: int, to_id: int, amount: float, source: str = "bank", description: str = "Перевод USD") -> str | None:
    if amount <= 0:
        return "Сумма должна быть больше нуля."
    sender = await get_user(db, from_id)
    receiver = await get_user(db, to_id)
    if not sender or not receiver:
        return "Игрок не найден."
    field = "usd_cash" if source == "cash" else "usd_bank"
    if sender[field] < amount:
        return "Недостаточно средств."
    await db.execute(f"UPDATE users SET {field}={field}-? WHERE telegram_id=?", (amount, from_id))
    await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (amount, to_id))
    await log_tx(db, from_id, to_id, amount, "USD", "transfer", description)
    await db.commit()
    return None


async def change_balance(db: aiosqlite.Connection, user_id: int, amount: float, field: str, reason: str, kind: str = "system") -> str | None:
    row = await get_user(db, user_id)
    if not row:
        return "Игрок не найден."
    if field not in {"usd_cash", "usd_bank", "crypto_btc", "crypto_eth", "crypto_usdt"}:
        return "Недопустимый счёт."
    if row[field] + amount < 0:
        return "Недостаточно средств."
    await db.execute(f"UPDATE users SET {field}={field}+? WHERE telegram_id=?", (amount, user_id))
    updated = await get_user(db, user_id)
    currency = "USD" if field.startswith("usd") else field.replace("crypto_", "").upper()
    await db.execute(
        "INSERT INTO balance_history(user_id, change_amount, currency, reason, balance_after) VALUES(?,?,?,?,?)",
        (user_id, amount, currency, reason, updated[field] if updated else 0),
    )
    await db.execute(
        "INSERT INTO transactions(from_user, to_user, amount, currency, type, description) VALUES(?,?,?,?,?,?)",
        (None if amount > 0 else user_id, user_id if amount > 0 else None, abs(amount), currency, kind, reason),
    )
    await db.commit()
    return None


async def log_tx(db: aiosqlite.Connection, from_user: int | None, to_user: int | None, amount: float, currency: str, tx_type: str, description: str) -> None:
    await db.execute(
        "INSERT INTO transactions(from_user, to_user, amount, currency, type, description) VALUES(?,?,?,?,?,?)",
        (from_user, to_user, amount, currency, tx_type, description),
    )
    if from_user:
        sender = await get_user(db, from_user)
        await db.execute(
            "INSERT INTO balance_history(user_id, change_amount, currency, reason, balance_after) VALUES(?,?,?,?,?)",
            (from_user, -amount, currency, description, sender["usd_bank"] if sender and currency == "USD" else 0),
        )
    if to_user:
        receiver = await get_user(db, to_user)
        await db.execute(
            "INSERT INTO balance_history(user_id, change_amount, currency, reason, balance_after) VALUES(?,?,?,?,?)",
            (to_user, amount, currency, description, receiver["usd_bank"] if receiver and currency == "USD" else 0),
        )


async def exchange_crypto(db: aiosqlite.Connection, user_id: int, asset: str, amount: float, direction: str) -> str | None:
    asset = asset.upper()
    if asset not in settings.crypto_rates or amount <= 0:
        return "Неверная валюта или сумма."
    user = await get_user(db, user_id)
    if not user:
        return "Игрок не найден."
    rate = settings.crypto_rates[asset]
    field = f"crypto_{asset.lower()}"
    usd_value = amount * rate
    if direction == "buy":
        if user["usd_bank"] < usd_value:
            return "Недостаточно средств на банковском счёте."
        await db.execute(f"UPDATE users SET usd_bank=usd_bank-?, {field}={field}+? WHERE telegram_id=?", (usd_value, amount, user_id))
        await log_tx(db, user_id, None, usd_value, "USD", "purchase", f"Покупка {asset}")
    else:
        if user[field] < amount:
            return "Недостаточно криптовалюты."
        await db.execute(f"UPDATE users SET usd_bank=usd_bank+?, {field}={field}-? WHERE telegram_id=?", (usd_value, amount, user_id))
        await log_tx(db, None, user_id, usd_value, "USD", "transfer", f"Продажа {asset}")
    await db.commit()
    return None


async def issue_fine(db: aiosqlite.Connection, user_id: int, issued_by: int, amount: float, reason: str) -> str | None:
    if amount <= 0:
        return "Сумма штрафа должна быть больше нуля."
    if not await get_user(db, user_id):
        return "Игрок не найден."
    await db.execute("INSERT INTO fines(user_id, issued_by, amount, reason) VALUES(?,?,?,?)", (user_id, issued_by, amount, reason))
    await db.execute("INSERT INTO notifications(user_id, type, message) VALUES(?,?,?)", (user_id, "fine", f"Вам выписан штраф: ${amount:,.2f}. Причина: {reason}"))
    await db.commit()
    return None


async def pay_fine(db: aiosqlite.Connection, user_id: int, fine_id: int, source: str = "bank") -> str | None:
    fine = await one(db, "SELECT * FROM fines WHERE id=? AND user_id=? AND status='pending'", (fine_id, user_id))
    if not fine:
        return "Активный штраф не найден."
    field = "usd_cash" if source == "cash" else "usd_bank"
    user = await get_user(db, user_id)
    if not user or user[field] < fine["amount"]:
        return "Недостаточно средств."
    await db.execute(f"UPDATE users SET {field}={field}-? WHERE telegram_id=?", (fine["amount"], user_id))
    await db.execute("UPDATE fines SET status='paid' WHERE id=?", (fine_id,))
    await db.execute("UPDATE government_treasury SET balance=balance+?, last_updated=CURRENT_TIMESTAMP WHERE id=1", (fine["amount"],))
    await log_tx(db, user_id, None, fine["amount"], "USD", "fine", f"Оплата штрафа №{fine_id}")
    await db.commit()
    return None


async def create_deposit(db: aiosqlite.Connection, user_id: int, amount: float, days: int) -> str | None:
    rate = {7: 3, 30: 5, 90: 8}.get(days)
    if not rate:
        return "Недоступный срок вклада."
    user = await get_user(db, user_id)
    if not user or user["usd_bank"] < amount or amount <= 0:
        return "Недостаточно средств."
    ends = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (amount, user_id))
    await db.execute("INSERT INTO deposits(user_id, amount, rate, duration_days, ends_at) VALUES(?,?,?,?,?)", (user_id, amount, rate, days, ends))
    await log_tx(db, user_id, None, amount, "USD", "deposit", f"Открытие вклада на {days} дней")
    await db.commit()
    return None


async def create_loan(db: aiosqlite.Connection, user_id: int, amount: float, months: int = 3) -> str | None:
    if amount <= 0 or months <= 0:
        return "Неверная сумма или срок."
    rate = settings.loan_rate
    total = amount * (1 + rate / 100)
    due = (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds")
    await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (amount, user_id))
    await db.execute(
        "INSERT INTO loans(user_id, amount, rate, monthly_payment, remaining, due_date) VALUES(?,?,?,?,?,?)",
        (user_id, amount, rate, total / months, total, due),
    )
    await log_tx(db, None, user_id, amount, "USD", "loan", "Выдача кредита")
    await db.commit()
    return None


async def buy_business(db: aiosqlite.Connection, user_id: int, name: str, business_type: str) -> str | None:
    if business_type not in BUSINESS_TYPES:
        return "Такого типа бизнеса нет."
    price, income = BUSINESS_TYPES[business_type]
    user = await get_user(db, user_id)
    if not user or user["usd_bank"] < price:
        return "Недостаточно средств на банковском счёте."
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (price, user_id))
    await db.execute("INSERT INTO businesses(name, type, owner_id, income_per_hour, price) VALUES(?,?,?,?,?)", (name, business_type, user_id, income, price))
    await log_tx(db, user_id, None, price, "USD", "purchase", f"Покупка бизнеса: {name}")
    await db.commit()
    return None


async def collect_business_income(db: aiosqlite.Connection, user_id: int, business_id: int) -> str | None:
    row = await one(db, "SELECT * FROM businesses WHERE id=? AND owner_id=?", (business_id, user_id))
    if not row:
        return "Бизнес не найден."
    last = datetime.fromisoformat(row["last_collected_at"])
    hours = min(max((datetime.now() - last).total_seconds() / 3600, 0), 48)
    if hours < 1:
        return "Доход можно собрать минимум через один час."
    amount = round(hours * row["income_per_hour"] * (1 + (row["level"] - 1) * 0.25), 2)
    await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (amount, user_id))
    await db.execute("UPDATE businesses SET last_collected_at=CURRENT_TIMESTAMP WHERE id=?", (business_id,))
    await log_tx(db, None, user_id, amount, "USD", "transfer", f"Доход бизнеса: {row['name']}")
    await db.commit()
    return None


async def buy_real_estate(db: aiosqlite.Connection, user_id: int, label: str) -> str | None:
    item = REAL_ESTATE.get(label)
    if not item:
        return "Объект недвижимости не найден."
    typ, district, price, rent = item
    user = await get_user(db, user_id)
    if not user or user["usd_bank"] < price:
        return "Недостаточно средств."
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (price, user_id))
    await db.execute("INSERT INTO real_estate(name, type, district, owner_id, price, rent_price) VALUES(?,?,?,?,?,?)", (label, typ, district, user_id, price, rent))
    await log_tx(db, user_id, None, price, "USD", "purchase", f"Покупка недвижимости: {label}")
    await db.commit()
    return None


async def buy_vehicle(db: aiosqlite.Connection, user_id: int, label: str) -> str | None:
    item = VEHICLES.get(label)
    if not item:
        return "Транспорт не найден."
    brand, model, typ, price = item
    user = await get_user(db, user_id)
    if not user or user["usd_bank"] < price:
        return "Недостаточно средств."
    await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (price, user_id))
    await db.execute("INSERT INTO vehicles(owner_id, brand, model, plate_number, type, price) VALUES(?,?,?,?,?,?)", (user_id, brand, model, plate(), typ, price))
    await log_tx(db, user_id, None, price, "USD", "purchase", f"Покупка транспорта: {brand} {model}")
    await db.commit()
    return None


async def add_notification(db: aiosqlite.Connection, user_id: int, typ: str, message: str) -> None:
    await db.execute("INSERT INTO notifications(user_id, type, message) VALUES(?,?,?)", (user_id, typ, message))


# --- RBAC: роли и права компаний/фракций ---

COMPANY_PERMISSIONS = {
    "company.edit_profile",
    "company.invite",
    "company.kick",
    "company.roles.manage",
    "company.salaries.manage",
    "company.budget.manage",
    "company.stocks.manage",
    "company.delete",
}

FACTION_PERMISSIONS = {
    "faction.edit_profile",
    "faction.invite",
    "faction.kick",
    "faction.roles.manage",
    "faction.salaries.manage",
    "faction.budget.manage",
    "faction.delete",
}


def _perm_json(perms: set[str]) -> str:
    return json.dumps(sorted(perms))


def _perm_set(value: str | None) -> set[str]:
    if not value:
        return set()
    try:
        raw = json.loads(value)
        return {str(x) for x in raw}
    except Exception:
        return set()


async def ensure_default_roles_for_company(db: aiosqlite.Connection, company_id: int, owner_user_id: int) -> None:
    exists = await one(db, "SELECT id FROM company_roles WHERE company_id=? AND is_owner_role=1", (company_id,))
    if exists:
        return
    # владелец
    cur = await db.execute(
        "INSERT INTO company_roles(company_id, name, permissions_json, is_owner_role) VALUES(?,?,?,1)",
        (company_id, "Владелец", _perm_json(COMPANY_PERMISSIONS),),
    )
    owner_role_id = cur.lastrowid
    # участник
    cur = await db.execute(
        "INSERT INTO company_roles(company_id, name, permissions_json, is_owner_role) VALUES(?,?,?,0)",
        (company_id, "Участник", _perm_json(set()),),
    )
    member_role_id = cur.lastrowid
    await db.execute(
        "UPDATE company_employees SET role_id=? WHERE user_id=? AND company_id=?",
        (owner_role_id, owner_user_id, company_id),
    )
    await db.commit()


async def ensure_default_roles_for_faction(db: aiosqlite.Connection, faction_id: int, leader_user_id: int) -> None:
    exists = await one(db, "SELECT id FROM faction_roles WHERE faction_id=? AND is_owner_role=1", (faction_id,))
    if exists:
        return
    cur = await db.execute(
        "INSERT INTO faction_roles(faction_id, name, permissions_json, is_owner_role) VALUES(?,?,?,1)",
        (faction_id, "Лидер", _perm_json(FACTION_PERMISSIONS),),
    )
    leader_role_id = cur.lastrowid
    cur = await db.execute(
        "INSERT INTO faction_roles(faction_id, name, permissions_json, is_owner_role) VALUES(?,?,?,0)",
        (faction_id, "Участник", _perm_json(set()),),
    )
    member_role_id = cur.lastrowid
    await db.execute(
        "UPDATE faction_members SET role_id=? WHERE user_id=? AND faction_id=?",
        (leader_role_id, leader_user_id, faction_id),
    )
    await db.commit()


async def company_role(db: aiosqlite.Connection, role_id: int) -> aiosqlite.Row | None:
    return await one(db, "SELECT * FROM company_roles WHERE id=?", (role_id,))


async def faction_role(db: aiosqlite.Connection, role_id: int) -> aiosqlite.Row | None:
    return await one(db, "SELECT * FROM faction_roles WHERE id=?", (role_id,))


async def company_member_role_id(db: aiosqlite.Connection, company_id: int) -> int | None:
    row = await one(db, "SELECT id FROM company_roles WHERE company_id=? AND is_owner_role=0 ORDER BY id LIMIT 1", (company_id,))
    return int(row["id"]) if row else None


async def faction_member_role_id(db: aiosqlite.Connection, faction_id: int) -> int | None:
    row = await one(db, "SELECT id FROM faction_roles WHERE faction_id=? AND is_owner_role=0 ORDER BY id LIMIT 1", (faction_id,))
    return int(row["id"]) if row else None


async def company_has_permission(db: aiosqlite.Connection, user_id: int, company_id: int, permission: str) -> bool:
    row = await one(
        db,
        "SELECT ce.role_id, cr.permissions_json, c.owner_id "
        "FROM companies c "
        "LEFT JOIN company_employees ce ON ce.company_id=c.id AND ce.user_id=? "
        "LEFT JOIN company_roles cr ON cr.id=ce.role_id "
        "WHERE c.id=?",
        (user_id, company_id),
    )
    if not row:
        return False
    if row["owner_id"] == user_id:
        return True
    perms = _perm_set(row["permissions_json"])
    return permission in perms


async def faction_has_permission(db: aiosqlite.Connection, user_id: int, faction_id: int, permission: str) -> bool:
    row = await one(
        db,
        "SELECT fm.role_id, fr.permissions_json, f.leader_id "
        "FROM factions f "
        "LEFT JOIN faction_members fm ON fm.faction_id=f.id AND fm.user_id=? "
        "LEFT JOIN faction_roles fr ON fr.id=fm.role_id "
        "WHERE f.id=?",
        (user_id, faction_id),
    )
    if not row:
        return False
    if row["leader_id"] == user_id:
        return True
    perms = _perm_set(row["permissions_json"])
    return permission in perms


# --- Инвайты в организации ---

async def create_org_invite(
    db: aiosqlite.Connection,
    entity_type: str,
    entity_id: int,
    invited_user_id: int,
    invited_by_user_id: int,
    role_id: int | None = None,
) -> int:
    cur = await db.execute(
        "INSERT INTO org_invites(entity_type, entity_id, invited_user_id, invited_by_user_id, role_id) "
        "VALUES(?,?,?,?,?)",
        (entity_type, entity_id, invited_user_id, invited_by_user_id, role_id),
    )
    invite_id = cur.lastrowid
    await add_notification(
        db,
        invited_user_id,
        "invite",
        f"Вас пригласили в {entity_type} №{entity_id}. Используйте команду или кнопку в боте, чтобы принять или отклонить.",
    )
    await db.commit()
    return int(invite_id)


async def get_org_invite(db: aiosqlite.Connection, invite_id: int) -> aiosqlite.Row | None:
    return await one(db, "SELECT * FROM org_invites WHERE id=?", (invite_id,))


async def list_org_invites_for_user(db: aiosqlite.Connection, user_id: int) -> list[aiosqlite.Row]:
    return await all_rows(db, "SELECT * FROM org_invites WHERE invited_user_id=? AND status='pending' ORDER BY created_at DESC", (user_id,))


async def update_org_invite_status(db: aiosqlite.Connection, invite_id: int, status: str) -> None:
    await db.execute("UPDATE org_invites SET status=? WHERE id=?", (status, invite_id))
    await db.commit()


async def accept_company_invite(db: aiosqlite.Connection, invite: aiosqlite.Row) -> str | None:
    company_id = int(invite["entity_id"])
    user_id = int(invite["invited_user_id"])
    await update_org_invite_status(db, int(invite["id"]), "accepted")
    # выкинуть из прошлой компании
    await db.execute("DELETE FROM company_employees WHERE user_id=?", (user_id,))
    await db.execute("UPDATE users SET company_id=? WHERE telegram_id=?", (company_id, user_id))
    role_id = invite["role_id"] or await company_member_role_id(db, company_id)
    await db.execute(
        "INSERT OR REPLACE INTO company_employees(user_id, company_id, role, salary, role_id) VALUES(?,?,?,?,?)",
        (user_id, company_id, "Участник", 0, role_id),
    )
    await db.commit()
    return None


async def accept_faction_invite(db: aiosqlite.Connection, invite: aiosqlite.Row) -> str | None:
    faction_id = int(invite["entity_id"])
    user_id = int(invite["invited_user_id"])
    await update_org_invite_status(db, int(invite["id"]), "accepted")
    await db.execute("DELETE FROM faction_members WHERE user_id=?", (user_id,))
    await db.execute("UPDATE users SET faction_id=? WHERE telegram_id=?", (faction_id, user_id))
    role_id = invite["role_id"] or await faction_member_role_id(db, faction_id)
    await db.execute(
        "INSERT OR REPLACE INTO faction_members(user_id, faction_id, rank, salary, role_id) VALUES(?,?,?,?,?)",
        (user_id, faction_id, "Участник", 0, role_id),
    )
    await db.execute("UPDATE factions SET members_count=members_count+1 WHERE id=?", (faction_id,))
    await db.commit()
    return None


async def safe_delete_company(db: aiosqlite.Connection, company_id: int, owner_id: int) -> str | None:
    company = await one(db, "SELECT * FROM companies WHERE id=?", (company_id,))
    if not company:
        return "Компания не найдена."
    if company["owner_id"] != owner_id:
        return "Удалять компанию может только владелец."
    await db.execute("DELETE FROM company_employees WHERE company_id=?", (company_id,))
    await db.execute("UPDATE users SET company_id=NULL WHERE company_id=?", (company_id,))
    await db.execute("DELETE FROM stock_holdings WHERE company_id=?", (company_id,))
    await db.execute("DELETE FROM stock_market WHERE company_id=?", (company_id,))
    await db.execute("UPDATE businesses SET company_id=NULL WHERE company_id=?", (company_id,))
    await db.execute("DELETE FROM org_invites WHERE entity_type='company' AND entity_id=?", (company_id,))
    await db.execute("DELETE FROM company_roles WHERE company_id=?", (company_id,))
    await db.execute("DELETE FROM companies WHERE id=?", (company_id,))
    await db.commit()
    return None


async def safe_delete_faction(db: aiosqlite.Connection, faction_id: int, leader_id: int) -> str | None:
    faction = await one(db, "SELECT * FROM factions WHERE id=?", (faction_id,))
    if not faction:
        return "Фракция не найдена."
    if faction["leader_id"] != leader_id:
        return "Удалять фракцию может только лидер."
    await db.execute("DELETE FROM faction_members WHERE faction_id=?", (faction_id,))
    await db.execute("UPDATE users SET faction_id=NULL WHERE faction_id=?", (faction_id,))
    await db.execute("DELETE FROM org_invites WHERE entity_type='faction' AND entity_id=?", (faction_id,))
    await db.execute("DELETE FROM faction_roles WHERE faction_id=?", (faction_id,))
    await db.execute("DELETE FROM factions WHERE id=?", (faction_id,))
    await db.commit()
    return None


async def safe_delete_business(db: aiosqlite.Connection, business_id: int, owner_id: int) -> str | None:
    row = await one(db, "SELECT * FROM businesses WHERE id=?", (business_id,))
    if not row:
        return "Бизнес не найден."
    if row["owner_id"] != owner_id:
        return "Удалять бизнес может только владелец."
    await db.execute("DELETE FROM businesses WHERE id=?", (business_id,))
    await db.commit()
    return None

