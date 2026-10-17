"""Демо-база промокодов и кэшбэк-ставок.

В демо-режиме бот выводит реалистичные промокоды и кэшбэк-сервисы
(LetyShops, Backit) — это макет данных для разработки интерфейса.
В live-режиме источник должен быть подключён через официальные партнёрские
программы/Aggregator API; интерфейс сервиса (метод `find_codes`) не меняется.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import CashbackService, PromoCode

# ---------- Промокоды по маркетплейсам / категориям ----------
PROMO_CODES: list[PromoCode] = [
    PromoCode(
        code="WBDISCOUNT15", market="wb", category="электроника",
        discount_pct=15, min_amount=5000,
        description="Скидка 15% на электронику от 5 000 ₽",
        expires=datetime(2026, 12, 31), verified=True,
    ),
    PromoCode(
        code="TECH10", market="ozon", category="электроника",
        discount_pct=10, min_amount=3000,
        description="10% на технику от 3 000 ₽",
        expires=datetime(2026, 11, 30), verified=True,
    ),
    PromoCode(
        code="SHOES20", market="lamoda", category="обувь",
        discount_pct=20, min_amount=4000,
        description="Скидка 20% на обувь от 4 000 ₽",
        expires=datetime(2026, 10, 31), verified=True,
    ),
    PromoCode(
        code="HOME500", market="megamarket", category="дом",
        discount_amount=500, min_amount=3000,
        description="−500 ₽ на товары для дома от 3 000 ₽",
        expires=datetime(2026, 12, 31), verified=False,
    ),
]

# ---------- Кэшбэк-сервисы: ставки по площадкам ----------
CASHBACK_RATES: list[CashbackService] = [
    CashbackService(name="LetyShops", market="wb", rate_pct=2.5,
                    note="Начисление до 60 дней", url="https://letyshops.com"),
    CashbackService(name="LetyShops", market="ozon", rate_pct=1.5,
                    note="Начисление до 60 дней", url="https://letyshops.com"),
    CashbackService(name="Backit", market="wb", rate_pct=3.0,
                    note="Мгновенный вывод", url="https://backit.me"),
    CashbackService(name="Backit", market="ozon", rate_pct=2.0,
                    note="Мгновенный вывод", url="https://backit.me"),
    CashbackService(name="Cashback.ru", market="lamoda", rate_pct=5.0,
                    note="Выплата 1 раз в месяц", url="https://cashback.ru"),
    CashbackService(name="Megabonus", market="megamarket", rate_pct=2.0,
                    note="Промокоды на сайте", url="https://megabonus.com"),
]

# Бонусы площадок (в рублях на 1000 ₽ заказа)
MARKET_BONUSES: dict[str, int] = {
    "megamarket": 250,  # баллы «Спасибо» Сбербанка: 250 бонусов на 1000 ₽
    "wb": 0,
    "ozon": 0,
}


def find_codes(market: str, category: str = "") -> list[PromoCode]:
    """Возвращает актуальные промокоды для площадки."""
    now = datetime.now()
    out = []
    for c in PROMO_CODES:
        if c.market != market:
            continue
        if c.category and category and c.category != category:
            continue  # категория не совпала
        if c.expires and c.expires < now:
            continue  # просрочен
        out.append(c)
    return out


def get_cashback_services(market: str) -> list[CashbackService]:
    return [s for s in CASHBACK_RATES if s.market == market]


def market_bonus_per_1000(market: str) -> int:
    return MARKET_BONUSES.get(market, 0)