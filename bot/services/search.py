"""Сервис поиска: параллельный опрос маркетплейсов, кэширование, агрегация."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import Optional

from ..config import settings
from ..models import Offer, Product, SearchResult
from ..providers.base import BaseProvider
from ..providers.reviews_demo import get_reviews
from .analyzer import DealAnalyzer
from .cashback import CashbackCalculator
from .promo import PromoService
from .reviews import ReviewAnalyzer
from .savings import SavingsService
from .trust import TrustScorer
from .videos import VideoReviewService
from .vision import VisionRecognizer

log = logging.getLogger(__name__)


class SearchCache:
    """Простой TTL-кэш СЫРЫХ офферов поиска (аналитика применяется при выдаче)."""

    def __init__(self, ttl_sec: int = 600, max_entries: int = 512) -> None:
        self.ttl = ttl_sec
        self.max = max_entries
        self._store: OrderedDict[str, tuple[float, list[Offer]]] = OrderedDict()

    def _key(self, query: str, providers: tuple[str, ...]) -> str:
        raw = f"{query.strip().lower()}::{','.join(sorted(providers))}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def get(self, query: str, providers: tuple[str, ...]) -> Optional[list[Offer]]:
        key = self._key(query, providers)
        item = self._store.get(key)
        if not item:
            return None
        ts, offers = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return offers

    def set(self, query: str, providers: tuple[str, ...], offers: list[Offer]) -> None:
        key = self._key(query, providers)
        self._store[key] = (time.time(), offers)
        self._store.move_to_end(key)
        while len(self._store) > self.max:
            self._store.popitem(last=False)


class SearchService:
    """Координирует поиск по всем подключенным провайдерам."""

    def __init__(
        self,
        providers: dict[str, BaseProvider],
        db=None,
    ) -> None:
        self.providers = providers
        self.cache = SearchCache(ttl_sec=settings.search_cache_ttl_sec)
        # Аналитика подключается в main; без неё поиск работает, но без бейджей
        self.analyzer: DealAnalyzer | None = None
        self.trust = TrustScorer()
        self.reviews = ReviewAnalyzer()
        self.promo = PromoService()
        self.cashback = CashbackCalculator()
        self.videos = VideoReviewService()
        self.savings: SavingsService | None = None
        self.vision: VisionRecognizer | None = None
        if db is not None:
            self.analyzer = DealAnalyzer(db)
            self.savings = SavingsService(db)

    async def search_by_image(self, image_bytes: bytes) -> tuple[str, SearchResult]:
        """Поиск по фото: распознать объект → искать по тексту.

        Возвращает (распознанный_запрос, результат_поиска).
        """
        if self.vision is None:
            raise RuntimeError("Распознавание изображений не настроено")
        query = (await self.vision.recognize(image_bytes)).strip().lower()
        result = await self.search(query)
        return query, result

    async def search(self, query: str, limit_per_market: Optional[int] = None) -> SearchResult:
        limit = limit_per_market or settings.search_results_per_market
        providers_tuple = tuple(self.providers.keys())

        if not query.strip():
            return SearchResult()

        cached = self.cache.get(query, providers_tuple)
        if cached is not None:
            # Кэш хранит сырые офферы; аналитика применяется при каждой выдаче,
            # чтобы история цен и Trust Score были свежими
            return await self._assemble(cached)

        tasks = [self._safe_search(p, query, limit) for p in self.providers.values()]
        results = await asyncio.gather(*tasks)

        all_offers: list[Offer] = []
        for offers in results:
            all_offers.extend(offers)
        self.cache.set(query, providers_tuple, all_offers)
        return await self._assemble(all_offers)

    async def _assemble(self, all_offers: list[Offer]) -> SearchResult:
        """Анализ + агрегация сырых офферов в итоговый результат."""
        # Блок «Охота за выгодами»: история цен, фейковые скидки, аномалии, trust
        if self.analyzer is not None and all_offers:
            all_offers = await self.analyzer.analyze(all_offers)
        # Блок «Защита от скама»: анализ отзывов (в демо-режиме — из каталога)
        for offer in all_offers:
            if offer.market and offer.product_id:
                reviews = get_reviews(offer.market, offer.product_id)
                if reviews:
                    offer.review_analysis = self.reviews.analyze_reviews(reviews)
        # Блок «Выгоды»: промокоды и кэшбэк
        for offer in all_offers:
            offer.promo_codes = self.promo.find_for_offer(offer)
            offer.cashback_calc = self.cashback.calculate(offer)
        # Блок «Видео-обзоры»
        for offer in all_offers:
            offer.video_reviews = self.videos.find_for_offer(offer)
        for offer in all_offers:
            self.trust.score(offer)

        aggregated: list[Product] = []
        # Грубое сопоставление названий одного товара с разных площадок
        buckets: dict[str, list[Offer]] = {}
        for offer in all_offers:
            key = self._normalize(offer.title)
            buckets.setdefault(key, []).append(offer)

        for title, offers in buckets.items():
            aggregated.append(Product(name=offers[0].title, offers=offers))

        # Сортируем по лучшей (самой дешёвой) эффективной цене
        aggregated.sort(key=lambda p: p.best.effective_price if p.best else 10**9)
        return SearchResult(products=aggregated)

    async def _safe_search(self, provider: BaseProvider, query: str, limit: int) -> list[Offer]:
        """Ошибка одного провайдера не роняет весь поиск."""
        try:
            return await provider.search(query, limit=limit)
        except Exception as exc:  # noqa: BLE001
            log.warning("Поиск через %s упал: %s", provider.label, exc)
            return []

    @staticmethod
    def _normalize(title: str) -> str:
        """Грубое сопоставление названий одного товара с разных площадок."""
        import re

        t = title.lower()
        t = re.sub(r"[^\w\sа-яёa-z0-9]", " ", t)
        words = [w for w in t.split() if len(w) > 2]
        return " ".join(sorted(set(words)))