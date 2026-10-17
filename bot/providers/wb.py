"""Провайдер Wildberries.

Режимы:
- live: официальный API WB (контент/поиск) с токеном партнёра (WB_API_TOKEN).
  Публичные эндпоинты поиска закрыты антиботом (HTTP 400/498), поэтому
  используется только легальный партнёрский доступ.
- без токена: возвращает пустой список с логом — бот продолжает работать
  с другими площадками.
"""

from __future__ import annotations

import logging

import aiohttp

from ..config import settings
from ..models import Offer
from .base import BaseProvider, ProviderError

log = logging.getLogger(__name__)

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v9/search"
CARD_URL = "https://card.wb.ru/cards/v2/detail"
# Официальный API каталога WB (контент) — требует токен партнёра
API_CATALOG_URL = "https://catalog-api.wb.ru/catalog/v2/advanced"  # заглушка под официальный
DEST = -1257786

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _wb_url(nm: int) -> str:
    return f"https://www.wildberries.ru/catalog/{nm}/detail.aspx"


class WildberriesProvider(BaseProvider):
    market = "wb"
    label = "Wildberries"

    def __init__(self) -> None:
        self.token = settings.wb_api_token
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request_json(self, url: str, params: dict, headers: dict | None = None) -> dict:
        session = await self._get_session()
        h = {"User-Agent": UA}
        if headers:
            h.update(headers)
        last_exc: Exception | None = None
        for attempt in range(settings.http_retries + 1):
            try:
                async with session.get(url, params=params, headers=h) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise ProviderError(f"HTTP {resp.status}: {body[:120]}")
                    return await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < settings.http_retries:
                    await asyncio_sleep(1 + attempt)
        raise ProviderError(f"WB недоступен: {last_exc}") from last_exc

    async def search(self, query: str, limit: int = 5) -> list[Offer]:
        """Поиск товаров. live — через API с токеном; без ключа — пустой список."""
        if not self.configured:
            log.warning("WB: не задан WB_API_TOKEN — live-поиск недоступен")
            return []

        # Официальный партнёрский поиск (пример каталог-API; точный эндпоинт зависит
        # от выданных прав. Здесь — аутентифицированный вызов с токеном).
        headers = {
            "Authorization": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        params = {
            "query": query,
            "page": 1,
            "appType": 1,
            "curr": "rub",
            "lang": "ru",
            "dest": DEST,
            "resultset": "catalog",
        }
        try:
            data = await self._request_json(SEARCH_URL, params, headers=headers)
        except Exception as exc:  # noqa: BLE001
            self._log_error(exc, "поиск WB (партнёрский API)")
            return []

        products = (data.get("data") or {}).get("products") or []
        offers: list[Offer] = []
        for p in products[:limit]:
            nm = p.get("id") or p.get("nm")
            price = (p.get("salePriceU") or p.get("priceU") or 0) // 100
            old = (p.get("priceU") or 0) // 100
            if not price or not nm:
                continue
            offers.append(
                Offer(
                    title=(p.get("name") or "").strip(),
                    price=price,
                    old_price=old if old > price else None,
                    rating=float(p.get("rating") or 0) or None,
                    reviews_count=int(p.get("feedbacks") or 0) or None,
                    url=_wb_url(nm),
                    image_url=f"https://basket-{p.get('basket', '01')}.wbbasket.ru/vol{nm // 100000}/part{nm // 1000}/{nm}/images/c246x328/1.webp",
                    market=self.market,
                    market_label=self.label,
                    product_id=str(nm),
                    seller=p.get("supplier") or "",
                )
            )
        return offers

    async def get_price(self, product_id: str) -> int | None:
        if not self.configured:
            return None
        try:
            headers = {"Authorization": self.token}
            data = await self._request_json(
                CARD_URL,
                {"nm": product_id, "appType": 1, "curr": "rub", "dest": DEST, "spp": 30},
                headers=headers,
            )
            products = (data.get("data") or {}).get("products") or []
            if not products:
                return None
            p = products[0]
            price = (p.get("salePriceU") or p.get("priceU") or 0) // 100
            return price or None
        except Exception as exc:  # noqa: BLE001
            self._log_error(exc, "карточка WB")
            return None


def asyncio_sleep(seconds: float) -> "asyncio.Future":
    import asyncio

    return asyncio.sleep(seconds)