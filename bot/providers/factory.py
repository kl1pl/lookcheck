"""Фабрика провайдеров: собирает активные маркетплейсы в один пул."""

from __future__ import annotations

from ..config import settings
from .base import BaseProvider
from .aliexpress import AliExpressProvider
from .demo import DemoProvider
from .ozon import OzonProvider
from .wb import WildberriesProvider


def build_providers() -> dict[str, BaseProvider]:
    """Возвращает словарь {market: provider} в зависимости от режима."""
    providers: dict[str, BaseProvider] = {}
    if settings.is_demo:
        providers["demo"] = DemoProvider(refresh_prices=True)
    else:
        for market in settings.supported_markets:
            if market == "wb":
                providers["wb"] = WildberriesProvider()
            elif market == "ozon":
                providers["ozon"] = OzonProvider()
            elif market == "aliexpress":
                providers["aliexpress"] = AliExpressProvider()
    return providers