"""Провайдер Ozon.

Работает через официальный Ozon Seller API (требует Client-Id и Api-Key
зарегистрированного продавца/партнёра — задаются в .env: OZON_CLIENT_ID,
OZON_API_KEY). Публичный поисковый API у Ozon закрыт, поэтому прямое
скрейп-обращение к ozon.ru не используется.
"""

from __future__ import annotations

import logging

import aiohttp

from ..config import settings
from ..models import Offer
from .base import BaseProvider, ProviderError

log = logging.getLogger(__name__)

SEARCH_URL = "https://api-seller.ozon.ru/v1/product/list"
INFO_URL = "https://api-seller.ozon.ru/v1/product/info"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _ozon_url(offer_id: str) -> str:
    return f"https://www.ozon.ru/product/{offer_id}"


class OzonProvider(BaseProvider):
    market = "ozon"
    label = "Ozon"

    def __init__(self) -> None:
        self.client_id = settings.ozon_client_id
        self.api_key = settings.ozon_api_key
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": UA,
        }

    async def _post(self, url: str, payload: dict) -> dict:
        if not self.configured:
            raise ProviderError("Ozon API не сконфигурирован (нужны OZON_CLIENT_ID и OZON_API_KEY)")
        session = await self._get_session()
        last_exc: Exception | None = None
        for attempt in range(settings.http_retries + 1):
            try:
                async with session.post(url, json=payload, headers=self._headers()) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise ProviderError(f"Ozon HTTP {resp.status}: {body[:200]}")
                    return await resp.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < settings.http_retries:
                    await asyncio_sleep(1 + attempt)
        raise ProviderError(f"Ozon недоступен: {last_exc}") from last_exc

    async def search(self, query: str, limit: int = 5) -> list[Offer]:
        offers: list[Offer] = []
        # Ozon Seller API: поиск по каталогу продавца (полнотекстового
        # покупательского поиска у API нет — это ограничение платформы).
        # Работает только с ключами; без них — пустой список, бот продолжает
        # работать с остальными площадками.
        if not self.configured:
            log.warning("Ozon: не заданы OZON_CLIENT_ID/OZON_API_KEY — live-поиск недоступен")
            return []

        try:
            data = await self._post(
                SEARCH_URL,
                {"filter": {"search": query}, "limit": limit, "sort_dir": "ASC"},
            )
            items = data.get("result", {}).get("items", []) or []
            for it in items[:limit]:
                price = int(it.get("price") or 0)
                if not price:
                    continue
                offers.append(
                    Offer(
                        title=it.get("name") or "",
                        price=price,
                        old_price=int(it.get("old_price")) if it.get("old_price") else None,
                        url=_ozon_url(it.get("offer_id", "")),
                        market=self.market,
                        market_label=self.label,
                        product_id=str(it.get("product_id") or it.get("offer_id") or ""),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self._log_error(exc, "Ozon API недоступен или не сконфигурирован")
        return offers

    async def get_price(self, product_id: str) -> int | None:
        try:
            data = await self._post(INFO_URL, {"product_id": int(product_id)})
            price = data.get("result", {}).get("price") or data.get("result", {}).get("min_price")
            return int(price) if price else None
        except Exception as exc:  # noqa: BLE001
            self._log_error(exc, "инфо о товаре")
            return None


def asyncio_sleep(seconds: float):
    import asyncio

    return asyncio.sleep(seconds)