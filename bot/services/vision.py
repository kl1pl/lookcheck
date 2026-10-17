"""Распознавание объекта на фото → поисковый запрос.

Интерфейс: `VisionRecognizer.recognize(image_bytes) -> str` (текстовое описание
товара для поиска).

Реализации:
- `DemoVisionRecognizer` (по умолчанию): эвристика по цвету/размеру/наличию
  прозрачности — возвращает реалистичный запрос по «доминирующему» типу товара.
  Нужен, чтобы весь конвейер (фото → запрос → поиск → ответ) работал офлайн.
- `LiveVisionRecognizer`: заглушка-интерфейс под vision-API (Yandex Vision /
  GigaChat Vision). В live-режиме сюда передаётся изображение, и сервис
  опознаёт товар (например, «беспроводные наушники»).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from PIL import Image
from io import BytesIO

log = logging.getLogger(__name__)

# Демо-каталог: (цвет, категория_товара, поисковый_запрос)
# Порядок важен: проверка «наушники» (тёмные, маленькие) идёт раньше остальных.
_DEMO_RULES = [
    (lambda r, g, b, size: size < 40_000 and r < 80 and g < 80 and b < 80, "наушники"),
    (lambda r, g, b, size: r > 120 and g < 90 and b < 90, "кроссовки красные"),
    (lambda r, g, b, size: r > 130 and g > 130 and b > 130, "кроссовки белые"),
    (lambda r, g, b, size: b > 100 and b > r and b > g, "смартфон синий"),
    (lambda r, g, b, size: r > 90 and g > 90 and b < 90, "наушники бежевые"),
    (lambda r, g, b, size: True, "смартфон"),
]


class VisionRecognizer(ABC):
    @abstractmethod
    async def recognize(self, image_bytes: bytes) -> str:
        """Возвращает текстовый запрос для поиска по изображению."""


class DemoVisionRecognizer(VisionRecognizer):
    """Эвристика по статистике пикселей — работает без внешних API."""

    async def recognize(self, image_bytes: bytes) -> str:
        try:
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            img.thumbnail((64, 64))
            pixels = list(img.getdata())
            n = len(pixels)
            avg_r = sum(p[0] for p in pixels) // n
            avg_g = sum(p[1] for p in pixels) // n
            avg_b = sum(p[2] for p in pixels) // n
            # Прозрачность/светлость ⩾ 90% — возможно, скриншот с белым фоном
            size = img.size[0] * img.size[1]

            # Пытаемся найти первое совпадение по правилам
            for rule, query in _DEMO_RULES:
                try:
                    if rule(avg_r, avg_g, avg_b, size):
                        return query
                except Exception:
                    continue
            return "смартфон"
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось распознать фото (%s), использую запрос по умолчанию", exc)
            return "смартфон"


class LiveVisionRecognizer(VisionRecognizer):
    """Заглушка для vision-API (Yandex Vision / GigaChat Vision)."""

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.api_key = api_key
        self.model = model

    async def recognize(self, image_bytes: bytes) -> str:
        # TODO(live): POST изображения в vision-API, вернуть описание товара.
        raise NotImplementedError("LiveVisionRecognizer: подключите vision-API")


def build_recognizer() -> VisionRecognizer:
    from ..config import settings

    if settings.is_demo:
        return DemoVisionRecognizer()
    return LiveVisionRecognizer()