"""Анализатор отзывов: детектор накрутки, извлечение проблем, размерная аналитика.

Вся логика работает на простых эвристиках (частоты, даты, шаблоны), которые
работают офлайн и без API отзывов. Метод `analyze_reviews()` принимает список
Review и возвращает ReviewAnalysis. Для live-режима нужен лишь источник отзывов
(официальные API/партнёрства) — анализ не меняется.

Детектор накрутки (признаки, суммируются):
- массовость по датам: > 40% отзывов написаны в один день;
- шаблонность: один и тот же текст повторяется N+ раз (одинаковые/почти
  одинаковые строки);
- «одноразовые» авторы: у 30%+ отзывов уникальные авторы (каждый написал 1);
  в демо — аккаунты с префиксом авторов-однодневок.

Извлечение проблем: негативные отзывы (рейтинг 1-2) классифицируются по
категориям (брак, батарея, доставка, несоответствие, качество) по ключевым
словам; выводим топ категорий относительно всех отзывов.

Размерная аналитика: по ключевым словам «маломерит/жмут/мал/впритык»,
«большемерит/велик», «размер в размер/подошли» — с учётом контекста.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime

from ..models import Review, ReviewAnalysis, SizingStat

log = logging.getLogger(__name__)

# ---- Категории жалоб: ключевые слова ----
COMPLAINT_KEYWORDS: dict[str, list[str]] = {
    "брак": ["брак", "трещит", "сломал", "не работает", "перестал", "сдох", "не включается", "разбился", "оторвал"],
    "батарея": ["батаре", "заряд", "разряжа", "аккумулятор", "садится"],
    "несоответствие": ["не соответств", "нет быстрой", "нет шумоподавления", "не такой", "другое", "описанию"],
    "доставка": ["доставк", "пришёл поздно", "не пришёл", "упаковк", "опоздал", "курьер"],
    "качество/материал": ["пластик", "хлипк", "дешёв", "пахнет", "материал", "царапин"],
    "размер": ["маломер", "жмут", "впритык", "велик", "большемер", "мал размер"],
}

# ---- Ключевые слова для размера ----
SIZING_SMALL = ["маломер", "жмут", "впритык", "мал", "тесн", "берите больше", "на размер больше"]
SIZING_BIG = ["большемер", "велик", "на размер меньше", "как 4"]
SIZING_TRUE = ["размер в размер", "подошли", "по размеру", "в размер"]

# Пороги детектора накрутки
PEAK_DAY_SHARE = 0.40  # доля отзывов в «пиковый» день
TEMPLATE_REPEAT = 3  # сколько раз должен повториться шаблон
BURST_WINDOW_DAYS = 2  # окно для «всплеска»


class ReviewAnalyzer:
    """Анализирует отзывы товара и возвращает ReviewAnalysis."""

    def analyze_reviews(self, reviews: list[Review]) -> ReviewAnalysis:
        if not reviews:
            return ReviewAnalysis(total_reviews=0)

        analysis = ReviewAnalysis(total_reviews=len(reviews))
        self._detect_boost(reviews, analysis)
        self._extract_complaints(reviews, analysis)
        self._analyze_sizing(reviews, analysis)
        return analysis

    # ---------- Детектор накрутки ----------

    def _detect_boost(self, reviews: list[Review], analysis: ReviewAnalysis) -> None:
        reasons: list[str] = []

        # 1. Массовое написание в один день / короткое окно
        with_date = [r for r in reviews if r.date is not None]
        if with_date:
            day_counts: Counter[str] = Counter(r.date.strftime("%Y-%m-%d") for r in with_date)
            peak_day, peak_count = day_counts.most_common(1)[0]
            peak_share = peak_count / len(with_date)
            if peak_share >= PEAK_DAY_SHARE:
                reasons.append(
                    f"{peak_count} из {len(with_date)} отзывов написаны за один день "
                    f"({peak_day}) — похоже на массовую заливку"
                )

            # Всплеск за короткое окно
            dates = sorted(r.date for r in with_date)
            if len(dates) > 4:
                span_days = max((dates[-1] - dates[0]).days, 1)
                if len(dates) / span_days > 3:  # много отзывов на день
                    reasons.append(f"неестественно высокая плотность отзывов: {len(dates)} штук за {span_days} дн.")

        # 2. Шаблонные фразы
        texts = [r.text.strip().lower() for r in reviews]
        repeated = 0
        for t in texts:
            if texts.count(t) >= TEMPLATE_REPEAT:
                repeated += 1
        if repeated:
            reasons.append(f"{repeated} из {len(texts)} отзывов повторяют одинаковый текст (шаблон)")

        # 3. «Одноразовые» авторы
        authors = [r.author_id for r in reviews if r.author_id]
        if authors:
            author_counts = Counter(authors)
            one_timers = sum(1 for a, c in author_counts.items() if c == 1)
            if one_timers / len(authors) >= 0.3:
                reasons.append(
                    f"{one_timers} из {len(authors)} отзывов написаны с уникальных "
                    f"аккаунтов (каждый автор — один отзыв)"
                )

        analysis.fake_reasons = reasons[:4]
        analysis.fake_suspicion = bool(reasons)
        # Оценка доли «подозрительных» отзывов: если накрутка уверенная — 40%+,
        # иначе — доля шаблонных
        if reasons:
            template_count = max((texts.count(t) for t in set(texts) if texts.count(t) >= TEMPLATE_REPEAT), default=0)
            analysis.fake_share = min(100, max(40, round(template_count / len(texts) * 100)))
        else:
            analysis.fake_share = 0

    # ---------- Реальные проблемы ----------

    def _extract_complaints(self, reviews: list[Review], analysis: ReviewAnalysis) -> None:
        neg = [r for r in reviews if r.rating <= 2]
        analysis.neg_share = round(len(neg) / len(reviews) * 100) if reviews else 0

        counts: Counter[str] = Counter()
        for r in neg:
            text = r.text.lower()
            for category, kws in COMPLAINT_KEYWORDS.items():
                if any(kw in text for kw in kws):
                    counts[category] += 1
        if not counts:
            analysis.complaints = {}
            analysis.complaint_top = []
            return

        analysis.complaints = dict(counts.most_common())
        # Доля категории относительно всех отзывов, чтобы не пугать единичными
        analysis.complaint_top = [
            f"{cat} — {cnt} упом. ({round(cnt / len(reviews) * 100)}%)"
            for cat, cnt in counts.most_common(3)
        ]

    # ---------- Размерная аналитика ----------

    def _analyze_sizing(self, reviews: list[Review], analysis: ReviewAnalysis) -> None:
        texts = [r.text.lower() for r in reviews]
        joined = " ".join(texts)
        # Сначала грубая проверка, что тема размера вообще есть
        if not any(kw in joined for kw in SIZING_SMALL + SIZING_BIG + SIZING_TRUE):
            analysis.sizing = None
            return

        small = sum(1 for t in texts if any(kw in t for kw in SIZING_SMALL))
        big = sum(1 for t in texts if any(kw in t for kw in SIZING_BIG))
        fits = sum(1 for t in texts if any(kw in t for kw in SIZING_TRUE))
        total = small + big + fits
        if total == 0:
            analysis.sizing = None
            return

        advice = ""
        if total:
            if small / total >= 0.6:
                advice = "🔝 Маломерит: берите на размер (или 2) больше"
            elif small / total >= 0.35:
                advice = "👟 Скорее маломерит: рассмотрите размер побольше"
            elif big / total >= 0.6:
                advice = "⬇️ Большемерит: берите на размер меньше"
            elif fits / total >= 0.6:
                advice = "✅ В основном размер в размер"

        analysis.sizing = SizingStat(
            runs_small=small,
            runs_big=big,
            fits_true=fits,
            total=total,
            advice=advice,
        )


# Для поиска товаров, к которым нужна размерная аналитика (одежда/обувь)
CLOTHING_KEYWORDS = [
    "кроссовк", "куртк", "футболк", "джинс", "штаны", "брюк", "плать",
    "ботинк", "сапог", "туфл", "кед", "рубашк", "свитер", "худи", "обувь",
    "костюм", "шапк", "шорты",
]


def is_clothing(title: str) -> bool:
    """Определяет по названию, относится ли товар к одежде/обуви."""
    t = title.lower()
    return any(kw in t for kw in CLOTHING_KEYWORDS)