"""Проверка продавца: эвристический Trust Score (0..100).

В MVP нет доступа к данным продавцов (возраст магазина, % возвратов) —
используем доступные сигналы из карточки товара:
- рейтинг товара;
- количество отзывов (очень мало отзывов — риск);
- предупреждения площадки/провайдера (warning);
- наличие признаков накрутки (заполняется аналитиком отзывов в будущем).

Скоринг консервативный: низкий доверительный уровень данных снижает оценку.
"""

from __future__ import annotations

from ..models import Offer


class TrustScorer:
    """Вычисляет Trust Score оффера и короткие бейджи-замечания."""

    def __init__(self) -> None:
        pass

    def score(self, offer: Offer) -> int:
        """Возвращает Trust Score 0..100 и заполняет offer.trust_badges."""
        points = 50.0  # нейтральный старт
        badges: list[str] = []

        # Рейтинг товара — главный сигнал
        if offer.rating is not None:
            points += (offer.rating - 3.5) * 20  # 3.5 => 0, 5.0 => +30
            if offer.rating < 3.5:
                badges.append("низкий рейтинг")
        else:
            points -= 10
            badges.append("нет рейтинга")

        # Объём отзывов: совсем нет — риск, мало — осторожность
        if offer.reviews_count is None:
            points -= 15
            badges.append("нет отзывов")
        elif offer.reviews_count < 10:
            points -= 15
            badges.append("очень мало отзывов")
        elif offer.reviews_count < 100:
            points -= 5

        # Предупреждение от провайдера/площадки
        if offer.warning:
            points -= 20
            badges.append("пометка площадки")

        # Явные аналитические флаги (заполнены DealAnalyzer)
        if offer.fake_discount:
            points -= 10
            badges.append("сомнительная скидка")
        if offer.price_anomaly:
            # Аномально низкая цена — не вина продавца, но риск отмены заказа
            points -= 5
            badges.append("аномальная цена")

        # Анализ отзывов (ReviewAnalysis), если есть
        ra = offer.review_analysis
        if ra is not None and ra.total_reviews:
            if ra.fake_suspicion:
                points -= 25
                badges.append("отзывы похожи на накрутку")
            if ra.neg_share >= 30:
                points -= 12
                badges.append("много негатива")
            elif ra.neg_share >= 15:
                points -= 5
            if ra.complaint_top:
                points -= 3

        score = max(0, min(100, round(points)))
        offer.trust_score = score
        offer.trust_badges = badges[:3]
        return score

    def verdict(self, score: int) -> tuple[str, str]:
        """(эмодзи-статус, текстовая характеристика)."""
        if score >= 80:
            return "✅", "Надёжный"
        if score >= 60:
            return "🟡", "Средний — проверьте отзывы"
        if score >= 40:
            return "⚠️", "Подозрительный — осторожно"
        return "🚫", "Не рекомендуется к покупке"