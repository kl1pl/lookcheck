"""Демо-провайдер: реалистичный каталог в памяти.

Используется по умолчанию (PROVIDER_MODE=demo), чтобы бот работал «из коробки»
без доступа к API маркетплейсов: поиск, сравнение цен, избранное и трекер цен
полностью функциональны. Замена на живые данные — одна строка в .env.
"""

from __future__ import annotations

import random
from typing import Optional

from ..models import Offer
from .base import BaseProvider

MARKETS = {
    "wb": ("Wildberries", "🟣", "https://www.wildberries.ru/catalog/{id}/detail.aspx"),
    "ozon": ("Ozon", "🔵", "https://www.ozon.ru/product/{id}"),
    "yandex": ("Яндекс Маркет", "🟡", "https://market.yandex.ru/product--/ {id}"),
    "megamarket": ("Мегамаркет", "🟠", "https://megamarket.ru/catalog/details/{id}"),
    "lamoda": ("Lamoda", "🔴", "https://www.lamoda.ru/p/{id}/"),
    "aliexpress": ("AliExpress", "🔴", "https://aliexpress.ru/item/{id}.html"),
}

CATALOG: dict[str, list[Offer]] = {
    "наушники": [
        Offer(
            title="Беспроводные наушники TWS Pro (Bluetooth 5.3, шумоподавление)",
            price=3900, old_price=5900, rating=4.7, reviews_count=1234,
            product_id="wb-1001", market="wb", market_label="Wildberries",
            url="https://www.wildberries.ru/catalog/1001/detail.aspx", seller="TechStore",
        ),
        Offer(
            title="Наушники TWS Pro (беспроводные, ENC)",
            price=4500, old_price=None, rating=4.8, reviews_count=2567,
            product_id="ozon-2001", market="ozon", market_label="Ozon",
            url="https://www.ozon.ru/product/2001", seller="Ozon Fresh",
        ),
        Offer(
            title="TWS наушники Pro — шумоподавление, 30ч работы",
            price=4800, old_price=6500, rating=4.5, reviews_count=890,
            product_id="mm-3001", market="megamarket", market_label="Мегамаркет",
            url="https://megamarket.ru/catalog/details/3001", seller="Elektronika",
        ),
        Offer(
            title="TWS наушники с ANC (копия обычного бренда, дешевле)",
            price=2400, old_price=4900, rating=3.2, reviews_count=315,
            product_id="ae-4001", market="aliexpress", market_label="AliExpress",
            url="https://aliexpress.ru/item/4001.html", seller="SuperCheap",
            warning="Рейтинг низкий; возможно, не оригинал",
        ),
    ],
    "смартфон": [
        Offer(
            title="Смартфон X 128GB (6.5\")",
            price=21000, old_price=25000, rating=4.6, reviews_count=890,
            product_id="wb-2002", market="wb", market_label="Wildberries",
            url="https://www.wildberries.ru/catalog/2002/detail.aspx", seller="MobileShop",
        ),
        Offer(
            title="Смартфон X 128GB (официальная гарантия)",
            price=22800, old_price=None, rating=4.8, reviews_count=1200,
            product_id="ozon-2002", market="ozon", market_label="Ozon",
            url="https://www.ozon.ru/product/2002", seller="DigitalPro",
        ),
        Offer(
            title="Смартфон X 128GB",
            price=19999, old_price=26999, rating=4.4, reviews_count=540,
            product_id="ym-2002", market="yandex", market_label="Яндекс Маркет",
            url="https://market.yandex.ru/product--/2002", seller="YandexShop",
        ),
    ],
    "кроссовки": [
        Offer(
            title="Кроссовки беговые Run 45 (размер 39-45)",
            price=3200, old_price=4200, rating=4.5, reviews_count=2100,
            product_id="wb-3003", market="wb", market_label="Wildberries",
            url="https://www.wildberries.ru/catalog/3003/detail.aspx", seller="SportLine",
        ),
        Offer(
            title="Кроссовки Run 45 для бега",
            price=3800, old_price=None, rating=4.7, reviews_count=980,
            product_id="lm-3003", market="lamoda", market_label="Lamoda",
            url="https://www.lamoda.ru/p/3003/", seller="Lamoda",
        ),
        Offer(
            title="Кроссовки беговые Run 45 (аналог)",
            price=2100, old_price=3100, rating=3.5, reviews_count=412,
            product_id="ae-3003", market="aliexpress", market_label="AliExpress",
            url="https://aliexpress.ru/item/3003.html", seller="ShoesDirect",
            warning="Качество может отличаться от оригинала",
        ),
    ],
    "ноутбук": [
        Offer(
            title="Ноутбук Pro 15.6\"/16GB/512GB",
            price=54900, old_price=65900, rating=4.8, reviews_count=740,
            product_id="wb-4004", market="wb", market_label="Wildberries",
            url="https://www.wildberries.ru/catalog/4004/detail.aspx", seller="Notebooks",
        ),
        Offer(
            title="Ноутбук Pro 15.6\"/16GB/512GB (гарантия 12 мес)",
            price=57900, old_price=None, rating=4.9, reviews_count=1500,
            product_id="ozon-4004", market="ozon", market_label="Ozon",
            url="https://www.ozon.ru/product/4004", seller="TechHouse",
        ),
    ],
    "кофеварка": [
        Offer(
            title="Кофеварка капельная 1.2л",
            price=1800, old_price=2400, rating=4.3, reviews_count=650,
            product_id="wb-5005", market="wb", market_label="Wildberries",
            url="https://www.wildberries.ru/catalog/5005/detail.aspx", seller="HomeTech",
        ),
        Offer(
            title="Кофеварка капельная 1.5л",
            price=2100, old_price=None, rating=4.6, reviews_count=320,
            product_id="ozon-5005", market="ozon", market_label="Ozon",
            url="https://www.ozon.ru/product/5005", seller="CoffeeLab",
        ),
    ],
}


class DemoProvider(BaseProvider):
    market = "demo"
    label = "Демо"

    def __init__(self, refresh_prices: bool = False) -> None:
        self._refresh = refresh_prices

    async def search(self, query: str, limit: int = 5) -> list[Offer]:
        q = query.strip().lower()
        for key, offers in CATALOG.items():
            if key in q or q in key:
                result = list(offers)
                if self._refresh:
                    # имитация живой цены: лёгкое «дыхание» ценой
                    for o in result:
                        o.price = max(1, int(o.price * random.uniform(0.97, 1.03)))
                return result[:limit]
        return []

    async def get_price(self, product_id: str) -> Optional[int]:
        for offers in CATALOG.values():
            for o in offers:
                if o.product_id == product_id:
                    if self._refresh:
                        return max(1, int(o.price * random.uniform(0.97, 1.03)))
                    return o.price
        return None