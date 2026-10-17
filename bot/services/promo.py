"""Сервис подбора промокодов: демо-источник + интерфейс для живого.

`find_codes_for_offer()` отбирает актуальные промокоды для конкретного
предложения: подходит площадка, цена попадает в минимум, категория (если
известна) совпадает. В live-режиме источником станет агрегатор промокодов
через официальные партнёрства.
"""

from __future__ import annotations

from ..models import Offer, PromoCode
from ..providers.promo_demo import find_codes

# Словарь: ключевые слова в названии -> категория каталога
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "электроника": ["наушник", "смартфон", "телефон", "ноутбук", "планшет", "колонк", "телевизор", "часы"],
    "обувь": ["кроссовк", "ботинк", "сапог", "туфл", "кед", "обувь"],
    "дом": ["кофеварк", "чайник", "микроволнов", "пылесос", "утюг", "полотенц", "посуда"],
}


def detect_category(title: str) -> str:
    """Определяет категорию каталога по названию товара."""
    t = title.lower()
    for category, kws in CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return category
    return ""


class PromoService:
    """Находит актуальные промокоды для оффера."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], list[PromoCode]] = {}

    def find_for_offer(self, offer: Offer) -> list[PromoCode]:
        """Промокоды, применимые к данному предложению."""
        category = detect_category(offer.title)
        key = (offer.market, category)
        if key not in self._cache:
            self._cache[key] = find_codes(offer.market, category)
        codes = []
        for c in self._cache[key]:
            if c.min_amount and offer.price < c.min_amount:
                continue
            codes.append(c)
        return codes

    def find_for_market(self, market: str) -> list[PromoCode]:
        """Все актуальные промокоды площадки (для команды /promo)."""
        return find_codes(market, "")