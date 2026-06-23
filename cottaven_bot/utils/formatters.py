from __future__ import annotations

from datetime import datetime
from html import escape

from config import E, SEP, THIN


def h(value: object) -> str:
    return escape("" if value is None else str(value))


def money(value: float | int | None) -> str:
    return f"${float(value or 0):,.2f}"


def dt(value: str | None = None) -> str:
    if not value:
        moment = datetime.now()
    else:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return h(value)
    return moment.strftime("%d.%m.%Y · %H:%M")


def header(title: str, subtitle: str = "COTTAVEN RP · Los Angeles") -> str:
    return f"╔══════════════════════════════╗\n║  {h(title)[:26]:<26}  ║\n║  {h(subtitle)[:26]:<26}  ║\n╚══════════════════════════════╝"


def ok(text: str) -> str:
    return f"✅ Успешно: {h(text)}"


def err(text: str) -> str:
    return f"⚠️ Ошибка: {h(text)}"


def empty(title: str, hint: str = "Здесь пока нет данных.") -> str:
    return f"{E['lamp']} <b>{h(title)}</b>\n{SEP}\n{h(hint)}"


def page_nav(page: int, total: int) -> str:
    return f"{THIN}\nСтраница {page + 1} из {max(total, 1)}"


def badge(role: str | None, gov_position: str | None = None) -> str:
    if role == "owner":
        return E["badge_owner"]
    if role == "admin":
        return E["badge_admin"]
    if role == "gov" or gov_position:
        return E["badge_gov"]
    return E["badge_user"]
