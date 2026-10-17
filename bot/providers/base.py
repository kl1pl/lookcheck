"""Базовый интерфейс провайдера маркетплейса."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..models import Offer

log = logging.getLogger(__name__)

MARKET_LABELS = {
    "wb": "Wildberries",
    "ozon": "Ozon",
    "yandex": "Яндекс Маркет",
    "megamarket": "Мегамаркет",
    "lamoda": "Lamoda",
    "aliexpress": "AliExpress",
    "dns": "DNS",
}


class ProviderError(Exception):
    """Ошибка при обращении к маркетплейсу."""


class BaseProvider(ABC):
    """Единый интерфейс: все провайдеры умеют искать товары по тексту."""

    market: str = ""
    label: str = ""

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[Offer]:
        """Поиск товаров по текстовому запросу."""

    @abstractmethod
    async def get_price(self, product_id: str) -> int | None:
        """Актуальная цена на конкретный товар (для трекера цен)."""

    def _log_error(self, exc: Exception, context: str = "") -> None:
        log.warning("Провайдер %s: ошибка %s: %s", self.label, context, exc)