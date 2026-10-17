"""Сервис видео-обзоров товара.

Демо-источник: каталог обзоров по категориям (наушники, смартфоны, кроссовки,
ноутбуки). В live-режиме подключается поиск по YouTube/TikTok API —
интерфейс `find_for_offer()` не меняется. Ссылки в демо — плейсхолдеры
(реальные видео подставляются через API).
"""

from __future__ import annotations

from ..models import Offer, VideoReview

# демо-каталог: категория -> обзоры
_VIDEOS: dict[str, list[VideoReview]] = {
    "наушники": [
        VideoReview(
            title="Беспроводные наушники TWS — подробный обзор и сравнение",
            url="https://www.youtube.com/watch?v=demo-01",
            source="YouTube", duration="12:34", views=245000, author="ТехноБлог",
        ),
        VideoReview(
            title="TWS Pro: честный тест шумоподавления",
            url="https://www.tiktok.com/@demo/video/01",
            source="TikTok", duration="01:12", views=890000, author="gadget_ru",
        ),
    ],
    "смартфон": [
        VideoReview(
            title="Смартфон X 128GB — обзор через месяц использования",
            url="https://www.youtube.com/watch?v=demo-02",
            source="YouTube", duration="18:20", views=512000, author="MobileReview",
        ),
    ],
    "обувь": [
        VideoReview(
            title="Кроссовки Run 45 — тест-драйв и размерная сетка",
            url="https://www.youtube.com/watch?v=demo-03",
            source="YouTube", duration="09:45", views=98000, author="SportTech",
        ),
    ],
    "ноутбук": [
        VideoReview(
            title="Ноутбук Pro 15.6 — обзор и тесты производительности",
            url="https://www.youtube.com/watch?v=demo-04",
            source="YouTube", duration="21:10", views=210000, author="NotebookLab",
        ),
    ],
}

# ключевые слова в названии оффера -> категория
_KEYWORDS: dict[str, list[str]] = {
    "наушники": ["наушник", "tws", "гарнитур"],
    "смартфон": ["смартфон", "телефон"],
    "обувь": ["кроссовк", "ботинк", "обувь", "кед"],
    "ноутбук": ["ноутбук", "laptop"],
}


class VideoReviewService:
    """Находит видео-обзоры для оффера."""

    def find_for_offer(self, offer: Offer) -> list[VideoReview]:
        t = offer.title.lower()
        for category, kws in _KEYWORDS.items():
            if any(kw in t for kw in kws):
                return _VIDEOS.get(category, [])
        return []