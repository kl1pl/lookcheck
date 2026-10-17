"""Провайдер AliExpress (Open Platform).

Использует официальный API AliExpress Open Platform (не требует ИНН/юрлица —
доступен индивидуальным разработчикам). Запросы подписываются (HMAC-SHA256)
и идут на gateway.aliexpress.com/openapi. Нужны ключи AE_APP_KEY (App Key)
и AE_APP_SECRET (App Secret) — задаются в .env.

Без ключей провайдер мягко возвращает пустой список (бот работает дальше).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse

import aiohttp

from ..config import settings
from ..models import Offer
from .base import BaseProvider

log = logging.getLogger(__name__)

GATEWAY = "https://gw.aliexpress.com/openapi/param2/1/global.aliexpress.open.popular"


def _ae_url(product_id: str) -> str:
    return f"https://aliexpress.ru/item/{product_id}.html"


class AliExpressProvider(BaseProvider):
    market = "aliexpress"
    label = "AliExpress"

    def __init__(self) -> None:
        self.app_key = settings.ae_app_key
        self.app_secret = settings.ae_app_secret
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.http_timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _sign(self, params: dict) -> str:
        """Подпись AliExpress Open Platform: метод+время+ключ, HMAC-SHA256."""
        method = "global.aliexpress.open.popular"
        timestamp = str(int(time.time() * 1000))
        sign_str = f"{method}{timestamp}{self.app_key}"
        digest = hmac.new(
            self.app_secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()
        params["_aop_timestamp"] = timestamp
        params["_aop_signature"] = digest
        return digest

    async def search(self, query: str, limit: int = 5) -> list[Offer]:
        """Поиск товаров через официальный гейтвей (популярные/поиск)."""
        if not self.configured:
            log.warning("AliExpress: не заданы AE_APP_KEY/AE_APP_SECRET — live-поиск недоступен")
            return []

        # Состав запроса зависит от доступного метода аккаунта (поиск или popular).
        # Базовый набор параметров общий для passerby API.
        params = {
            "app_key": self.app_key,
            "key": query,
            "page": "1",
            "pageSize": str(min(limit, 40)),
            "sort": "default",
            "shipToCountry": "RU",
            "format": "json",
            "sign_method": "sha256",
            "_aop_str": "",
        }
        self._sign(params)

        offers: list[Offer] = []
        try:
            session = await self._get_session()
            url = GATEWAY + "?" + urllib.parse.urlencode(params)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=settings.http_timeout_sec)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self._log_error(ProviderError(f"HTTP {resp.status}: {body[:120]}"), "поиск AE")
                    return []
                data = await resp.json(content_type=None)

            # Ответ алейэкспресс: {"aliexpress_affiliate_productdetail_get_response": ...}
            # или {"error_response": {...}}. Вариации полей зависят от метода.
            items = []
            if isinstance(data, dict):
                for key in ("aliexpress_affiliate_productdetail_get_response",
                            "aliexpress_affiliate_productquery_response",
                            "aliexpress_affiliate_hotproduct_query_response"):
                    resp_block = data.get(key)
                    if resp_block:
                        items = (resp_block.get("result", {}).get("products", {})
                                 or {}).get("product", []) or []
                        break

            for it in items[:limit]:
                pid = str(it.get("product_id") or "")
                price = int(float(it.get("target_sale_price") or it.get("sale_price") or 0) * 100)
                if not pid or not price:
                    continue
                offers.append(
                    Offer(
                        title=it.get("subject_merge") or it.get("product_title") or "",
                        price=max(1, price),
                        rating=float(it.get("evaluations", 0)) if it.get("evaluations") else None,
                        url=_ae_url(pid),
                        image_url=it.get("product_main_image_url") or "",
                        market=self.market,
                        market_label=self.label,
                        product_id=pid,
                        seller="AliExpress",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self._log_error(exc, "гейтвей AliExpress")
        return offers

    async def get_price(self, product_id: str) -> int | None:
        """Не реализовано в базовом наборе методов — трекер опирается на поиск."""
        return None


class ProviderError(Exception):
    """Локальная ошибка провайдера (избегаем конфликта имён)."""