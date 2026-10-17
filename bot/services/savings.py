"""Сервис экономии пользователя.

Считает, сколько денег сэкономил пользователь благодаря боту:
- скидка (разница между зачёркнутой и реальной ценой, если скидка честная);
- кэшбэк (лучший сервис + бонусы площадки);
- аномалия цены (пойманный «баг»/распродажа — засчитывается отдельно).

Запись и агрегация — через БД (таблица savings). Вывод — команда /stats.
"""

from __future__ import annotations

import logging

from ..db import Database, DemoDatabase

log = logging.getLogger(__name__)

KIND_DISCOUNT = "discount"
KIND_CASHBACK = "cashback"
KIND_ANOMALY = "anomaly"


class SavingsService:
    """Регистрирует и агрегирует экономию пользователя."""

    def __init__(self, db: Database | DemoDatabase) -> None:
        self.db = db

    async def record_search_savings(self, user_id: int, offers: list) -> None:
        """Записывает экономию по всем офферам из выдачи (только явные выгоды)."""
        for offer in offers:
            # Скидка: только если она не выглядит фейковой
            if offer.old_price and offer.old_price > offer.price and not offer.fake_discount:
                await self.db.add_saving(
                    user_id, offer.market, offer.title[:80],
                    offer.old_price - offer.price, KIND_DISCOUNT,
                )
            # Кэшбэк: сервис + бонусы площадки
            cc = offer.cashback_calc
            if cc is not None:
                cb_total = cc.service_cashback + cc.market_bonus
                if cb_total > 0:
                    await self.db.add_saving(
                        user_id, offer.market, offer.title[:80], cb_total, KIND_CASHBACK,
                    )
            # Аномалия цены
            if offer.price_anomaly:
                await self.db.add_saving(
                    user_id, offer.market, offer.title[:80],
                    (offer.avg_price or offer.price) - offer.price if offer.avg_price else offer.price,
                    KIND_ANOMALY,
                )

    async def summary(self, user_id: int) -> dict[str, int]:
        return await self.db.get_savings_summary(user_id)

    async def recent(self, user_id: int, limit: int = 10) -> list:
        return await self.db.list_savings(user_id, limit)