from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        for text, data in row:
            builder.button(text=text, callback_data=data)
        builder.adjust(*[len(r) for r in rows])
    return builder.as_markup()


def profile_kb() -> InlineKeyboardMarkup:
    return kb([
        [("💎 Крипто кошелёк", "crypto:menu"), ("🚫 Штрафы", "fines:menu")],
        [("📈 История баланса", "history:all:0"), ("🏦 Банк", "bank:menu")],
        [("🏠 Недвижимость", "realestate:menu"), ("🚗 Транспорт", "vehicles:menu")],
        [("🏛 Фракция", "faction:mine"), ("🔥 Компания", "company:mine")],
        [("⭐ Достижения", "achievements:menu"), ("🔔 Уведомления", "notifications:menu")],
        [("📨 Приглашения", "invites:menu"), ("⚙️ Настройки", "settings:menu")],
        [("📊 Биржа", "stocks:menu")],
    ])


def company_manage_kb(company_id: int) -> InlineKeyboardMarkup:
    return kb([
        [("👥 Участники", f"company:members:{company_id}"), ("➕ Пригласить", f"company:invite:{company_id}")],
        [("🎭 Роли и права", f"company:roles:{company_id}"), ("✏️ Профиль", f"company:edit:{company_id}")],
        [("🗑 Удалить компанию", f"company:delete:{company_id}")],
        [("⬅️ Назад", "company:mine")],
    ])


def bank_kb() -> InlineKeyboardMarkup:
    return kb([
        [("💳 Мой счёт", "bank:account"), ("📈 Вклады", "bank:deposits")],
        [("💸 Кредиты", "bank:loans"), ("🔄 Перевод", "bank:transfer")],
        [("📋 История", "history:all:0"), ("💳 Карта", "bank:card")],
    ])


def crypto_kb() -> InlineKeyboardMarkup:
    return kb([
        [("₿ Bitcoin", "crypto:asset:BTC"), ("⬡ Ethereum", "crypto:asset:ETH")],
        [("₮ USDT", "crypto:asset:USDT"), ("🔄 Обменять", "crypto:exchange")],
        [("📤 Отправить", "crypto:send"), ("📋 История", "history:crypto:0")],
    ])


def confirm_kb(prefix: str, ident: int | str) -> InlineKeyboardMarkup:
    return kb([[("✅ Подтвердить", f"{prefix}:confirm:{ident}"), ("❌ Отмена", f"{prefix}:cancel:{ident}")]])


def admin_kb() -> InlineKeyboardMarkup:
    return kb([
        [("👤 Игроки", "admin:players"), ("🏛 Фракции", "admin:factions")],
        [("🏢 Компании", "admin:companies"), ("💰 Экономика", "admin:economy")],
        [("🏠 Недвижимость", "admin:estate"), ("📊 Статистика", "admin:stats")],
        [("📢 Рассылка", "admin:broadcast"), ("🔧 Система", "admin:system")],
    ])


def gov_kb(position: str | None = None) -> InlineKeyboardMarkup:
    rows = [[("🏛 Казна", "gov:treasury"), ("📋 Указы", "gov:decrees")]]
    if position in {"Президент", "Вице-Президент", "Министр Финансов", None}:
        rows.append([("👤 Назначения", "gov:appoint"), ("💰 Налоги", "gov:tax")])
    rows.extend([
        [("⚖️ Штрафы", "gov:fines"), ("📊 Статистика", "gov:stats")],
        [("🗳 Голосование", "gov:votes"), ("📜 Законопроекты", "gov:bills")],
        [("🔍 Расследование", "gov:investigate"), ("⚠️ ЧП", "gov:emergency")],
    ])
    return kb(rows)


def simple_menu(prefix: str, labels: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for idx, label in enumerate(labels):
        row.append((label, f"{prefix}:{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return kb(rows)
