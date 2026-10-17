"""Кэшбэк-калькулятор: реальная цена с учётом кэшбэк-сервисов и бонусов.

Расчёт: real_price = price − cashback_лучшего_сервиса − бонусы_площадки.

Пример из ТЗ: Мегамаркет 4 800₽ + 1 200 бонусов = реально 3 600₽ классически
считается как 4800 − 1200. Мы дополнительно показываем кэшбэк-сервисы
(LetyShops/Backit), чтобы пользователь видел максимальную экономию.
"""

from __future__ import annotations

from ..models import CashbackCalc, CashbackService, Offer
from ..providers.promo_demo import get_cashback_services, market_bonus_per_1000


class CashbackCalculator:
    """Считает реальную цену предложения."""

    def calculate(self, offer: Offer) -> CashbackCalc:
        services = get_cashback_services(offer.market)

        # Бонусы площадки: фиксированные баллы от цены (на 1000 ₽)
        bonus_rate = market_bonus_per_1000(offer.market)
        market_bonus = round(offer.price / 1000) * bonus_rate if bonus_rate else 0

        # Лучший кэшбэк-сервис по рублям
        best: CashbackService | None = None
        best_cash: int = 0
        for s in services:
            cash = round(offer.price * s.rate_pct / 100)
            if cash > best_cash:
                best_cash = cash
                best = s

        final = max(0, offer.price - best_cash - market_bonus)
        return CashbackCalc(
            original_price=offer.price,
            market=offer.market,
            services=services,
            best_service=best,
            service_cashback=best_cash,
            market_bonus=market_bonus,
            final_price=final,
            total_saving=(offer.price - final),
        )