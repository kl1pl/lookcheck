"""Модели данных, общие для бота и провайдеров."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Offer:
    """Одно найденное предложение на маркетплейсе."""

    title: str
    price: int  # в рублях
    old_price: Optional[int] = None  # зачёркнутая цена, если есть
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    url: str = ""
    image_url: str = ""
    market: str = ""  # wb | ozon | ...
    market_label: str = ""  # Wildberries | Ozon | ...
    product_id: str = ""  # внутренний id товара на площадке
    seller: str = ""
    cashback: int = 0  # бонусы/кэшбэк в рублях, если известно
    warning: str = ""

    # ---- Аналитика (заполняется сервисом анализа) ----
    trust_score: Optional[int] = None  # 0..100 Trust Score продавца
    trust_badges: list[str] = field(default_factory=list)  # короткие замечания
    fake_discount: bool = False  # объявленная «старая цена» недостоверна
    fake_discount_note: str = ""
    price_anomaly: bool = False  # цена заметно ниже исторической нормы
    price_anomaly_note: str = ""
    avg_price: Optional[int] = None  # средняя цена по истории наблюдений

    # ---- Анализ отзывов (заполняется ReviewAnalyzer) ----
    review_analysis: Optional["ReviewAnalysis"] = None

    # ---- Промокоды и кэшбэк (заполняются PromoService/CashbackCalculator) ----
    promo_codes: list["PromoCode"] = field(default_factory=list)
    cashback_calc: Optional["CashbackCalc"] = None

    # ---- Видео-обзоры ----
    video_reviews: list["VideoReview"] = field(default_factory=list)

    @property
    def effective_price(self) -> int:
        """Цена с учётом кэшбэка/бонусов."""
        return max(0, self.price - self.cashback)

    @property
    def card_url(self) -> str:
        return self.url or f"https://www.wildberries.ru/catalog/{self.product_id}/detail.aspx" if self.market == "wb" and self.product_id else (self.url or "")


@dataclass
class Product:
    """Агрегированный товар (одна позиция с нескольких площадок)."""

    name: str
    offers: list[Offer] = field(default_factory=list)

    @property
    def best(self) -> Optional[Offer]:
        return min(self.offers, key=lambda o: o.effective_price) if self.offers else None

    def sorted_offers(self) -> list[Offer]:
        return sorted(self.offers, key=lambda o: o.effective_price)


@dataclass
class SearchResult:
    products: list[Product] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.products


@dataclass
class User:
    user_id: int
    username: str = ""
    first_name: str = ""
    is_premium: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    daily_queries_used: int = 0
    queries_date: str = ""  # YYYY-MM-DD день, к которому относится счётчик


@dataclass
class Favorite:
    """Избранный товар для трекинга цены."""

    id: int = 0
    user_id: int = 0
    market: str = ""
    product_id: str = ""
    title: str = ""
    url: str = ""
    last_price: int = 0
    last_checked: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PriceHistory:
    """История цен на избранный товар."""

    id: int = 0
    favorite_id: int = 0
    price: int = 0
    checked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PriceStat:
    """Агрегированная статистика цены товара (для детектора скидок и аномалий)."""

    market: str = ""
    product_id: str = ""
    last_price: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    avg_price: Optional[int] = None
    samples: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class Review:
    """Один отзыв на товар."""

    text: str
    rating: int = 5  # 1..5
    date: Optional[datetime] = None  # дата написания (для детектора накрутки)
    author_id: str = ""  # анонимный id автора (для проверки массовости)


@dataclass
class SizingStat:
    """Размерная аналитика для одежды/обуви."""

    runs_small: int = 0  # «маломерит»
    runs_big: int = 0    # «большемерит»
    fits_true: int = 0   # «размер в размер»
    total: int = 0
    advice: str = ""     # рекомендация: на сколько размеров брать больше/меньше

    @property
    def small_pct(self) -> int:
        return round(self.runs_small / self.total * 100) if self.total else 0

    @property
    def big_pct(self) -> int:
        return round(self.runs_big / self.total * 100) if self.total else 0

    @property
    def true_pct(self) -> int:
        return round(self.fits_true / self.total * 100) if self.total else 0

    @property
    def has_data(self) -> bool:
        return self.total > 0


@dataclass
class ReviewAnalysis:
    """Результат анализа отзывов товара."""

    total_reviews: int = 0
    # Детектор накрутки
    fake_suspicion: bool = False
    fake_reasons: list[str] = field(default_factory=list)
    fake_share: int = 0  # % отзывов, похожих на накрутку
    # Реальные проблемы из негатива
    complaints: dict[str, int] = field(default_factory=dict)  # категория -> число упоминаний
    complaint_top: list[str] = field(default_factory=list)    # топ категорий
    neg_share: int = 0  # % негатива (рейтинг 1-2)
    # Размерная аналитика
    sizing: Optional[SizingStat] = None

    @property
    def has_sizing(self) -> bool:
        return self.sizing is not None and self.sizing.has_data


@dataclass
class PromoCode:
    """Промокод для конкретного маркетплейса/категории."""

    code: str
    market: str  # wb | ozon | ...
    description: str = ""
    discount_pct: int = 0  # % скидки (0 если фиксированная сумма)
    discount_amount: int = 0  # фиксированная скидка в рублях
    min_amount: int = 0  # минимальная сумма заказа
    category: str = ""  # категория, к которой применим (пусто — любая)
    expires: Optional[datetime] = None
    verified: bool = False  # проверен в последние N часов


@dataclass
class CashbackService:
    """Кэшбэк-сервис (LetyShops, Backit и т.п.) с ставкой по площадке."""

    name: str
    market: str  # для какой площадки ставка
    rate_pct: float = 0.0  # % от цены
    note: str = ""
    url: str = ""


@dataclass
class CashbackCalc:
    """Результат расчёта реальной цены с учётом кэшбэка и бонусов."""

    original_price: int = 0
    market: str = ""
    # Кэшбэк-сервисы
    services: list[CashbackService] = field(default_factory=list)
    best_service: Optional[CashbackService] = None
    service_cashback: int = 0  # в рублях по лучшему сервису
    # Бонусы площадки
    market_bonus: int = 0  # бонусные баллы в рублях (например, «Спасибо»)
    # Итог
    final_price: int = 0
    total_saving: int = 0

    @property
    def has_data(self) -> bool:
        return self.best_service is not None or self.market_bonus > 0


@dataclass
class SavingsEntry:
    """Запись об экономии пользователя (скидка, кэшбэк, аномалия)."""

    id: int = 0
    user_id: int = 0
    market: str = ""
    product: str = ""
    amount: int = 0  # рублей сэкономлено
    kind: str = ""  # discount | cashback | anomaly
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class VideoReview:
    """Видео-обзор товара (YouTube/TikTok)."""

    title: str
    url: str
    source: str = ""  # YouTube | TikTok | VK Video
    duration: str = ""  # "12:34"
    views: int = 0
    author: str = ""


@dataclass
class SearchEntry:
    """Запись в истории поиска пользователя."""

    id: int = 0
    user_id: int = 0
    query: str = ""
    results_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)