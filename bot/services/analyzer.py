"""Блок «Охота за выгодами»: детектор фейковых скидок и ловец аномалий цены.

Логика детектора:
1. У товара есть зачёркнутая «старая цена» (old_price) — проверяем её честность:
   - если старая цена выше исторического максимума наблюдаемых цен с запасом,
     это похоже на раздутую «базу» для скидки (fake discount);
   - если история показывает, что товар почти всегда продавался существенно
     дешевле заявленной скидки — предупреждаем.
2. Ловец багов цен: если текущая цена заметно ниже среднего/минимума истории
   (например, ошибка селлера), помечаем как аномалию — такие предложения
   выгодны, но нужно успеть.

Все расчёты консервативные: мы выдаём предупреждения, а не утверждения.
"""

from __future__ import annotations

import logging

from ..db import Database, DemoDatabase
from ..models import Offer, PriceStat

log = logging.getLogger(__name__)

# Порог: старая цена считается «раздутой», если превышает исторический максимум на 25%+
FAKE_DISCOUNT_MARGIN = 1.25
# Порог аномалии: текущая цена ниже среднего на 20%+ при минимум 3 наблюдениях
ANOMALY_DROP_RATIO = 0.80
ANOMALY_MIN_SAMPLES = 3


class DealAnalyzer:
    """Анализирует офферы, используя историю цен из БД."""

    def __init__(self, db: Database | DemoDatabase) -> None:
        self.db = db

    async def analyze(self, offers: list[Offer]) -> list[Offer]:
        """Записывает текущие цены в историю, помечает скидки/аномалии."""
        result: list[Offer] = []
        for offer in offers:
            await self._record(offer)
            stat = await self.db.get_price_stat(offer.market, offer.product_id)
            self._check_discount(offer, stat)
            self._check_anomaly(offer, stat)
            result.append(offer)
        return result

    async def _record(self, offer: Offer) -> None:
        if not offer.market or not offer.product_id or not offer.price:
            return
        await self.db.record_price(offer.market, offer.product_id, offer.price)

    def _check_discount(self, offer: Offer, stat: PriceStat | None) -> None:
        """Детектор фейковых скидок на основе истории цен."""
        if not offer.old_price or offer.old_price <= offer.price:
            offer.old_price = None
            return
        # Нет истории — нельзя судить; показываем скидку как есть
        if stat is None or stat.samples < 2 or stat.max_price is None:
            return
        # Если «старая цена» сильно выше того, что товар реально стоил
        if offer.old_price > stat.max_price * FAKE_DISCOUNT_MARGIN:
            offer.fake_discount = True
            offer.fake_discount_note = (
                f"Зачёркнутая цена {offer.old_price:,}₽ выше реального максимума "
                f"({stat.max_price:,}₽) — скидка может быть искусственной"
            ).replace(",", " ")
        # Если товар в истории почти всегда стоил около текущей цены
        elif stat.avg_price and offer.price >= stat.avg_price * 0.97:
            offer.fake_discount_note = (
                f"Товар обычно стоит около {stat.avg_price:,}₽ — «скидка» скорее "
                f"номинальная"
            ).replace(",", " ")

    def _check_anomaly(self, offer: Offer, stat: PriceStat | None) -> None:
        """Ловец багов цен: текущая цена заметно ниже исторической нормы."""
        if stat is None or stat.avg_price is None or stat.samples < ANOMALY_MIN_SAMPLES:
            return
        if offer.price <= stat.avg_price * ANOMALY_DROP_RATIO:
            offer.price_anomaly = True
            offer.price_anomaly_note = (
                f"Цена {offer.price:,}₽ на {round((1 - offer.price / stat.avg_price) * 100)}% "
                f"ниже средней ({stat.avg_price:,}₽) — похоже на ошибку продавца или "
                f"распродажу, успейте!"
            ).replace(",", " ")