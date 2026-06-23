from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _ids(value: str | None) -> set[int]:
    result: set[int] = set()
    for part in (value or "").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            result.add(int(part))
    return result


USE_PREMIUM_EMOJI = os.getenv("USE_PREMIUM_EMOJI", "0").strip().lower() in {"1", "true", "yes", "on"}


def ce(emoji_id: int, fallback: str) -> str:
    if not USE_PREMIUM_EMOJI:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


E = {
    "btc": ce(5816788957614053645, "₿"),
    "eth": ce(5816442632926140550, "⬡"),
    "usdt": ce(5814556334829343625, "₮"),
    "info": ce(5334544901428229844, "ℹ️"),
    "ban": ce(5240241223632954241, "🚫"),
    "invite": ce(5253742260054409879, "📨"),
    "up": ce(5244837092042750681, "📈"),
    "down": ce(5246762912428603768, "📉"),
    "gear": ce(5341715473882955310, "⚙️"),
    "edit": ce(5395444784611480792, "✏️"),
    "fire": ce(5424972470023104089, "🔥"),
    "home": ce(5416041192905265756, "🏠"),
    "plus": ce(5397916757333654639, "➕"),
    "shop": ce(5406683434124859552, "🛒"),
    "diamond": ce(5427168083074628963, "💎"),
    "star": ce(5438496463044752972, "⭐"),
    "crown": ce(5217822164362739968, "👑"),
    "lock": ce(5296369303661067030, "🔒"),
    "percent": ce(5229064374403998351, "%"),
    "gold": ce(5440539497383087970, "🥇"),
    "silver": ce(5447203607294265305, "🥈"),
    "bronze": ce(5453902265922376865, "🥉"),
    "loading": ce(5386367538735104399, "⏳"),
    "trash": ce(5445267414562389170, "🗑"),
    "confetti": ce(5461151367559141950, "🎉"),
    "bookmark": ce(5222444124698853913, "🔖"),
    "lamp": ce(5422439311196834318, "💡"),
    "bell": ce(5458603043203327669, "🔔"),
    "shield": ce(5251203410396458957, "🛡"),
    "arrows_up": ce(5449683594425410231, "⬆️"),
    "arrows_down": ce(5447183459602669338, "⬇️"),
    "warning": ce(5447644880824181073, "⚠️"),
    "red_warning": ce(5420323339723881652, "🚨"),
    "siren": ce(5395695537687123235, "🚨"),
    "boom": ce(5276032951342088188, "💥"),
    "chest": ce(5278467510604160626, "💰"),
    "money_bag": ce(5287231198098117669, "💰"),
    "cash": ce(5190827354309561962, "💵"),
    "dollars": ce(5197434882321567830, "💵"),
    "badge_user": ce(5339107153128994580, "👤"),
    "badge_gov": ce(5339395689031942456, "🏛"),
    "badge_admin": ce(5339265100551304952, "⚙️"),
    "badge_owner": ce(5339278947525868877, "👑"),
}


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: set[int] = field(default_factory=lambda: _ids(os.getenv("ADMIN_IDS")))
    admin_group_ids: set[int] = field(default_factory=lambda: _ids(os.getenv("ADMIN_GROUP_IDS")))
    news_channel_id: int | None = int(os.getenv("NEWS_CHANNEL_ID")) if (os.getenv("NEWS_CHANNEL_ID") or "").lstrip("-").isdigit() else None
    database_path: Path = Path(os.getenv("DATABASE_PATH", "cottaven.sqlite3"))
    parse_mode: str = "HTML"
    crypto_rates: dict[str, float] = field(default_factory=lambda: {"BTC": 68000.0, "ETH": 3600.0, "USDT": 1.0})
    loan_rate: float = 12.0
    business_tax: float = 5.0
    income_tax: float = 7.0
    property_tax: float = 1.0
    vehicle_tax: float = 1.0


settings = Settings()

SEP = "━━━━━━━━━━━━━━━━━━━━━━━━"
THIN = "────────────────────────────"

BUSINESS_TYPES = {
    "Заправка": (30000, 750),
    "Магазин": (18000, 420),
    "Ресторан": (26000, 620),
    "Ночной клуб": (60000, 1500),
    "Завод": (120000, 3200),
    "Автомойка": (14000, 330),
    "Аптека": (22000, 500),
    "Казино": (250000, 7500),
    "Отель": (90000, 2100),
    "Порт": (180000, 4800),
}

REAL_ESTATE = {
    "Студия": ("studio", "Даунтаун", 25000, 350),
    "Апартаменты": ("apartment", "Санта-Моника", 65000, 900),
    "Дом": ("house", "Венис", 140000, 1800),
    "Особняк": ("mansion", "Беверли-Хиллз", 650000, 7200),
    "Офис": ("office", "Финансовый квартал", 220000, 3100),
    "Склад": ("warehouse", "Порт Лос-Анджелеса", 175000, 2400),
    "Пентхаус": ("penthouse", "Голливуд", 900000, 9800),
}

VEHICLES = {
    "Dodge Charger": ("Dodge", "Charger", "sedan", 45000),
    "Ford Crown Victoria": ("Ford", "Crown Victoria", "police", 28000),
    "Tesla Model S": ("Tesla", "Model S", "electric", 85000),
    "Cadillac Escalade": ("Cadillac", "Escalade", "suv", 110000),
    "Peterbilt 579": ("Peterbilt", "579", "truck", 145000),
}

GOV_POSITIONS = [
    "Президент",
    "Вице-Президент",
    "Глава Сената",
    "Сенатор",
    "Генеральный Прокурор",
    "Министр Финансов",
    "Министр Юстиции",
    "Министр Обороны",
    "Глава Национальной Гвардии",
    "Директор ФБР",
    "Верховный Судья",
]
