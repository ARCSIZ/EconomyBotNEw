from __future__ import annotations

import random
from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from database.db import db as database
from database.models import add_notification, log_tx


async def notify(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception:
        logger.debug("Не удалось отправить уведомление {}", user_id)


async def accrue_business_income(bot: Bot) -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall("SELECT owner_id, SUM(income_per_hour * level * 6) AS amount FROM businesses GROUP BY owner_id")
        for row in rows:
            amount = round(row["amount"], 2)
            await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (amount, row["owner_id"]))
            await log_tx(db, None, row["owner_id"], amount, "USD", "transfer", "Автоматический доход бизнесов")
            await add_notification(db, row["owner_id"], "business", f"Начислен доход бизнесов: ${amount:,.2f}")
            await notify(bot, row["owner_id"], f"💰 Начислен доход бизнесов: ${amount:,.2f}")
        await db.commit()
    finally:
        await db.close()


async def process_deposits(bot: Bot) -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall("SELECT * FROM deposits WHERE status='active'")
        current = datetime.now()
        for row in rows:
            if datetime.fromisoformat(row["ends_at"]) <= current:
                payout = round(row["amount"] * (1 + row["rate"] / 100), 2)
                await db.execute("UPDATE deposits SET status='completed' WHERE id=?", (row["id"],))
                await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (payout, row["user_id"]))
                await log_tx(db, None, row["user_id"], payout, "USD", "deposit", f"Завершение вклада №{row['id']}")
                await notify(bot, row["user_id"], f"📈 Вклад №{row['id']} завершён. Зачислено ${payout:,.2f}")
        await db.commit()
    finally:
        await db.close()


async def process_loans(bot: Bot) -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall("SELECT * FROM loans WHERE status='active'")
        current = datetime.now()
        for row in rows:
            if datetime.fromisoformat(row["due_date"]) > current:
                continue
            user = await db.execute_fetchall("SELECT usd_bank FROM users WHERE telegram_id=?", (row["user_id"],))
            balance = user[0]["usd_bank"] if user else 0
            payment = min(row["monthly_payment"], row["remaining"])
            if balance >= payment:
                remaining = row["remaining"] - payment
                status = "paid" if remaining <= 0 else "active"
                next_due = (current + timedelta(days=30)).isoformat(timespec="seconds")
                await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (payment, row["user_id"]))
                await db.execute("UPDATE loans SET remaining=?, status=?, due_date=? WHERE id=?", (remaining, status, next_due, row["id"]))
                await log_tx(db, row["user_id"], None, payment, "USD", "loan", f"Платёж по кредиту №{row['id']}")
                await notify(bot, row["user_id"], f"💸 Списан платёж по кредиту №{row['id']}: ${payment:,.2f}")
            else:
                penalty = round(payment * 0.1, 2)
                await db.execute("UPDATE loans SET status='overdue' WHERE id=?", (row["id"],))
                await db.execute("INSERT INTO fines(user_id, issued_by, amount, reason) VALUES(?,?,?,?)", (row["user_id"], 0, penalty, f"Просрочка кредита №{row['id']}"))
                await notify(bot, row["user_id"], f"⚠️ Кредит №{row['id']} просрочен. Начислен штраф ${penalty:,.2f}")
        await db.commit()
    finally:
        await db.close()


async def update_stock_quotes() -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall("SELECT * FROM stock_market")
        for row in rows:
            factor = random.uniform(0.97, 1.04)
            price = max(1, round(row["price_per_share"] * factor, 2))
            await db.execute("UPDATE stock_market SET price_per_share=?, last_updated=CURRENT_TIMESTAMP WHERE id=?", (price, row["id"]))
        await db.commit()
    finally:
        await db.close()


async def process_property_taxes(bot: Bot) -> None:
    db = await database.connect()
    try:
        rate_row = await db.execute_fetchall("SELECT rate_percent FROM tax_rates WHERE type='property'")
        rate = float(rate_row[0]["rate_percent"]) if rate_row else 1.0
        rows = await db.execute_fetchall("SELECT * FROM real_estate WHERE owner_id IS NOT NULL")
        for row in rows:
            tax = round(row["price"] * rate / 100, 2)
            user = await db.execute_fetchall("SELECT usd_bank FROM users WHERE telegram_id=?", (row["owner_id"],))
            balance = user[0]["usd_bank"] if user else 0
            if balance >= tax:
                await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (tax, row["owner_id"]))
                await db.execute("UPDATE government_treasury SET balance=balance+?, last_updated=CURRENT_TIMESTAMP WHERE id=1", (tax,))
                await log_tx(db, row["owner_id"], None, tax, "USD", "tax", f"Налог на недвижимость: {row['name']}")
                await notify(bot, row["owner_id"], f"🏠 Списан налог на недвижимость {row['name']}: ${tax:,.2f}")
            else:
                penalty = round(tax * 2, 2)
                await db.execute("INSERT INTO fines(user_id, issued_by, amount, reason) VALUES(?,?,?,?)", (row["owner_id"], 0, penalty, f"Неуплата налога на недвижимость: {row['name']}"))
                await notify(bot, row["owner_id"], f"⚠️ Недостаточно средств для налога на недвижимость. Начислен штраф ${penalty:,.2f}")
        await db.commit()
    finally:
        await db.close()


async def process_vehicle_taxes(bot: Bot) -> None:
    db = await database.connect()
    try:
        rate_row = await db.execute_fetchall("SELECT rate_percent FROM tax_rates WHERE type='vehicle'")
        rate = float(rate_row[0]["rate_percent"]) if rate_row else 1.0
        rows = await db.execute_fetchall("SELECT * FROM vehicles WHERE owner_id IS NOT NULL")
        for row in rows:
            base = row["price"] or 10000
            tax = round(base * rate / 100, 2)
            user = await db.execute_fetchall("SELECT usd_bank FROM users WHERE telegram_id=?", (row["owner_id"],))
            balance = user[0]["usd_bank"] if user else 0
            if balance >= tax:
                await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (tax, row["owner_id"]))
                await db.execute("UPDATE government_treasury SET balance=balance+?, last_updated=CURRENT_TIMESTAMP WHERE id=1", (tax,))
                await log_tx(db, row["owner_id"], None, tax, "USD", "tax", f"Налог на транспорт: {row['brand']} {row['model']}")
                await notify(bot, row["owner_id"], f"🚗 Списан налог на транспорт {row['brand']} {row['model']}: ${tax:,.2f}")
            else:
                await db.execute("INSERT INTO fines(user_id, issued_by, amount, reason) VALUES(?,?,?,?)", (row["owner_id"], 0, round(tax * 1.5, 2), f"Неуплата транспортного налога: {row['brand']} {row['model']}"))
                await notify(bot, row["owner_id"], "⚠️ Недостаточно средств для транспортного налога. Начислен штраф.")
        await db.commit()
    finally:
        await db.close()


async def process_rents(bot: Bot) -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall("SELECT * FROM real_estate WHERE is_rented=1 AND renter_id IS NOT NULL AND owner_id IS NOT NULL")
        for row in rows:
            rent = row["rent_price"]
            renter = await db.execute_fetchall("SELECT usd_bank FROM users WHERE telegram_id=?", (row["renter_id"],))
            balance = renter[0]["usd_bank"] if renter else 0
            if balance >= rent:
                await db.execute("UPDATE users SET usd_bank=usd_bank-? WHERE telegram_id=?", (rent, row["renter_id"]))
                await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (rent, row["owner_id"]))
                await log_tx(db, row["renter_id"], row["owner_id"], rent, "USD", "rent", f"Аренда недвижимости: {row['name']}")
                await notify(bot, row["owner_id"], f"🏠 Получена аренда за {row['name']}: ${rent:,.2f}")
                await notify(bot, row["renter_id"], f"🏠 Списана аренда за {row['name']}: ${rent:,.2f}")
            else:
                await db.execute("UPDATE real_estate SET is_rented=0, renter_id=NULL WHERE id=?", (row["id"],))
                await notify(bot, row["renter_id"], f"⚠️ Аренда {row['name']} прекращена из-за нехватки средств.")
        await db.commit()
    finally:
        await db.close()


async def process_dividends(bot: Bot) -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall(
            """
            SELECT h.user_id, h.shares_count, s.price_per_share, c.name
            FROM stock_holdings h
            JOIN stock_market s ON s.company_id=h.company_id
            JOIN companies c ON c.id=h.company_id
            """
        )
        for row in rows:
            payout = round(row["shares_count"] * row["price_per_share"] * 0.01, 2)
            if payout <= 0:
                continue
            await db.execute("UPDATE users SET usd_bank=usd_bank+? WHERE telegram_id=?", (payout, row["user_id"]))
            await log_tx(db, None, row["user_id"], payout, "USD", "dividend", f"Дивиденды компании {row['name']}")
            await notify(bot, row["user_id"], f"📊 Начислены дивиденды {row['name']}: ${payout:,.2f}")
        await db.commit()
    finally:
        await db.close()


async def process_insurance(bot: Bot) -> None:
    db = await database.connect()
    try:
        rows = await db.execute_fetchall("SELECT * FROM insurance_policies WHERE status='active'")
        current = datetime.now()
        for row in rows:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires <= current:
                await db.execute("UPDATE insurance_policies SET status='expired' WHERE id=?", (row["id"],))
                await notify(bot, row["user_id"], f"🛡 Страховой полис №{row['id']} истёк.")
            elif expires - current <= timedelta(days=3):
                await notify(bot, row["user_id"], f"🛡 Страховой полис №{row['id']} истекает менее чем через 3 дня.")
        await db.commit()
    finally:
        await db.close()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(accrue_business_income, "interval", hours=6, args=[bot], id="business_income", replace_existing=True)
    scheduler.add_job(process_deposits, "interval", hours=24, args=[bot], id="deposits", replace_existing=True)
    scheduler.add_job(process_loans, "interval", hours=24, args=[bot], id="loans", replace_existing=True)
    scheduler.add_job(process_rents, "interval", hours=24, args=[bot], id="rents", replace_existing=True)
    scheduler.add_job(process_property_taxes, "interval", days=7, args=[bot], id="property_taxes", replace_existing=True)
    scheduler.add_job(process_vehicle_taxes, "interval", days=30, args=[bot], id="vehicle_taxes", replace_existing=True)
    scheduler.add_job(process_dividends, "interval", days=7, args=[bot], id="dividends", replace_existing=True)
    scheduler.add_job(update_stock_quotes, "interval", minutes=5, id="stock_quotes", replace_existing=True)
    scheduler.add_job(process_insurance, "interval", hours=1, args=[bot], id="insurance", replace_existing=True)
    scheduler.start()
    return scheduler
