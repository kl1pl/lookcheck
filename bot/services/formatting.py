"""Форматирование ответов бота: единый формат выдачи результатов поиска."""

from __future__ import annotations

from ..models import Offer, Product, SearchResult
from .trust import TrustScorer

MARKET_EMOJI = {
    "wb": "🟣",
    "ozon": "🔵",
    "yandex": "🟡",
    "megamarket": "🟠",
    "lamoda": "🔴",
    "aliexpress": "🔴",
    "demo": "🪙",
}


def _fmt_price(price: int) -> str:
    return f"{price:,}".replace(",", " ") + "₽"


def format_sources_status(is_demo: bool, configured: dict[str, bool]) -> str:
    """Честная маркировка источников: какие площадки реально подключены.

    configured: {market_label: bool} — True, если у провайдера есть ключи/доступ.
    """
    if is_demo:
        return (
            "🪙 <b>Режим демо:</b> цены учебные.\n"
            "Для реальных цен нужны ключи маркетплейсов (см. KEYS.md)."
        )

    missing = [name for name, ok in configured.items() if not ok]
    if not missing:
        return ""
    names = ", ".join(missing)
    return f"⚠️ <b>Нет доступа к:</b> {names}. Цены по ним не показываются."


def _offer_line(offer: Offer) -> str:
    emoji = MARKET_EMOJI.get(offer.market, "🛒")
    parts = [f"{emoji} {offer.market_label}: {_fmt_price(offer.price)}"]
    if offer.cashback:
        parts.append(f"− {_fmt_price(offer.cashback)} кэшбэк")
    if offer.rating:
        parts.append(f"Рейтинг: {offer.rating}")
    if offer.reviews_count:
        parts.append(f"Отзывы: {offer.reviews_count:,}".replace(",", " "))
    if offer.old_price and offer.old_price > offer.price:
        discount = round((1 - offer.price / offer.old_price) * 100)
        parts.append(f"скидка {discount}%")
    if offer.trust_score is not None:
        emoji_t, verdict = TrustScorer().verdict(offer.trust_score)
        parts.append(f"{emoji_t} Trust {offer.trust_score}/100")
    line = " | ".join(parts)

    notes: list[str] = []
    if offer.warning:
        notes.append(f"⚠️ {offer.warning}")
    if offer.fake_discount and offer.fake_discount_note:
        notes.append(f"🚩 {offer.fake_discount_note}")
    elif offer.fake_discount_note:  # скидка подозрительна, но не «фейк»
        notes.append(f"📌 {offer.fake_discount_note}")
    if offer.price_anomaly and offer.price_anomaly_note:
        notes.append(f"🚨 {offer.price_anomaly_note}")
    if notes:
        line += "\n" + "\n".join(notes)
    return line


def format_search_result(result: SearchResult, query: str, sources_note: str = "") -> str:
    if result.empty:
        text = (
            f"🔍 По запросу «{query}» ничего не найдено.\n"
            "Попробуйте изменить формулировку или проверьте позже."
        )
        if sources_note:
            text += "\n\n" + sources_note
        return text

    lines: list[str] = [f"🔍 Результаты поиска: «{query}»\n"]
    for idx, product in enumerate(result.products[:3], start=1):
        offers = product.sorted_offers()
        best = offers[0] if offers else None
        if not best:
            continue

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines.append(f"{medals.get(idx, '🔹')} {product.name}\n")

        if best:
            if best.effective_price != best.price:
                lines.append(
                    f"💎 Выгоднее всего: {_offer_line(best)} (реальная цена {_fmt_price(best.effective_price)})\n"
                )
            else:
                lines.append(f"💰 Лучшая цена: {_offer_line(best)}\n")

        for offer in offers[1:4]:
            lines.append(_offer_line(offer))

        # Блок «Защита от скама»: анализ отзывов лучшего предложения
        ra_block = _review_analysis_block(best)
        if ra_block:
            lines.append(ra_block)

        # Блок «Размерная аналитика» (если товар — одежда/обувь)
        sizing_block = _sizing_block(best)
        if sizing_block:
            lines.append(sizing_block)

        # Блок «Выгоды»: промокоды и кэшбэк
        benefits_block = _benefits_block(best)
        if benefits_block:
            lines.append(benefits_block)

        # Блок «Видео-обзоры»
        video_block = _video_block(best)
        if video_block:
            lines.append(video_block)

        lines.append("")
    text = "\n".join(lines).strip()
    if sources_note:
        text += "\n\n" + sources_note
    return text


def _video_block(offer: Offer) -> str:
    """Блок видео-обзоров товара."""
    if not offer.video_reviews:
        return ""
    lines = ["🎬 <b>Видео-обзоры:</b>"]
    for v in offer.video_reviews[:2]:
        views = f"{v.views:,}".replace(",", " ")
        lines.append(
            f"▶️ <a href=\"{v.url}\">{v.title}</a> — {v.source}, {v.duration}, {views} просмотров"
        )
    return "\n".join(lines)


def _benefits_block(offer: Offer) -> str:
    """Блок промокодов и кэшбэка — как сэкономить ещё больше."""
    parts: list[str] = []
    calc = offer.cashback_calc

    if calc is not None and calc.has_data:
        saving_parts = []
        if calc.best_service is not None:
            saving_parts.append(
                f"{calc.best_service.name}: −{_fmt_price(calc.service_cashback)} ({calc.best_service.rate_pct}%)"
            )
        if calc.market_bonus:
            saving_parts.append(f"бонусы площадки: −{_fmt_price(calc.market_bonus)}")
        parts.append("🎁 <b>Кэшбэк даст ещё:</b> " + ", ".join(saving_parts))
        if calc.final_price < offer.price:
            parts.append(
                f"💸 Реальная цена: {_fmt_price(offer.price)} → <b>{_fmt_price(calc.final_price)}</b> "
                f"(экономия {_fmt_price(calc.total_saving)})"
            )

    codes = [c for c in offer.promo_codes if c.verified]
    if codes:
        promo_line = " | ".join(
            f"<code>{c.code}</code> ({c.description})" for c in codes[:2]
        )
        parts.append(f"🏷 Промокоды: {promo_line}")
    return "\n".join(parts)


def format_promos(market: str, codes: list) -> str:
    """Команда /promo: список актуальных промокодов площадки."""
    from ..providers.base import MARKET_LABELS

    label = MARKET_LABELS.get(market, market)
    if not codes:
        return f"🏷 Для {label} сейчас нет активных промокодов."
    lines = [f"🏷 <b>Актуальные промокоды — {label}:</b>\n"]
    for c in codes:
        lines.append(f"<code>{c.code}</code> — {c.description}")
        lines.append(f"   ✓ Скидка: {c.discount_pct}%" if c.discount_pct else f"   ✓ Скидка: −{c.discount_amount}₽")
        if c.min_amount:
            lines.append(f"   ✓ от {_fmt_price(c.min_amount)}")
        if c.expires:
            lines.append(f"   ⏳ до {c.expires.strftime('%d.%m.%Y')}")
        if c.verified:
            lines.append("   ✅ проверен")
        lines.append("")
    return "\n".join(lines).strip()


def _review_analysis_block(offer: Offer) -> str:
    """Блок анализа отзывов: накрутка, жалобы, доля негатива."""
    ra = offer.review_analysis
    if ra is None or ra.total_reviews == 0:
        return ""
    parts: list[str] = []
    if ra.fake_suspicion and ra.fake_reasons:
        parts.append("🛡️ <b>Кажется, отзывы накручены:</b>")
        parts.extend(f"• {r}" for r in ra.fake_reasons[:3])
        parts.append(f"   ~{ra.fake_share}% отзывов похожи на шаблонные\n")
    if ra.complaint_top:
        parts.append(f"📋 <b>Частые жалобы ({ra.neg_share}% негатива):</b>")
        parts.extend(f"• {c}" for c in ra.complaint_top[:3])
    return "\n".join(parts)


def _sizing_block(offer: Offer) -> str:
    """Блок размерной аналитики для одежды/обуви."""
    ra = offer.review_analysis
    if ra is None or not ra.has_sizing:
        return ""
    s = ra.sizing
    lines = [
        "📏 <b>Размерная аналитика:</b>",
        f"• маломерит: {s.small_pct}%   • большемерит: {s.big_pct}%   • в размер: {s.true_pct}%",
    ]
    if s.advice:
        lines.append(f"💡 {s.advice}")
    return "\n".join(lines)


def format_offer(offer: Offer) -> str:
    """Формат отдельного предложения для избранного/трекинга."""
    emoji = MARKET_EMOJI.get(offer.market, "🛒")
    lines = [
        f"{emoji} {offer.title}",
        f"💰 {_fmt_price(offer.price)}" if offer.price else "",
        f"⭐ Рейтинг: {offer.rating}" if offer.rating else "",
        f"📦 Отзывы: {offer.reviews_count}" if offer.reviews_count else "",
        f"🧑‍💼 Продавец: {offer.seller}" if offer.seller else "",
        f"🔗 {offer.url}" if offer.url else "",
    ]
    return "\n".join(x for x in lines if x)


def format_favorites_list(items: list[tuple[int, str, str, int]]) -> str:
    """Список избранного: (id, название, ссылка, цена)."""
    if not items:
        return "⭐ В избранном пока пусто.\nНайдите товар и нажмите «Добавить в избранное»."
    lines = ["⭐ Ваше избранное:\n"]
    for fav_id, title, url, price in items:
        lines.append(f"{fav_id}. {title}\n   {_fmt_price(price)} | {url}")
    return "\n".join(lines)


def format_savings(summary: dict[str, int], recent: list) -> str:
    """Статистика экономии: /stats."""
    total = summary.get("total", 0)
    lines = [
        "💰 <b>Ваша экономия с LookCheck:</b>",
        f"🧮 Всего сэкономлено: <b>{_fmt_price(total)}</b>",
        "",
        f"🏷 За счёт скидок: {_fmt_price(summary.get('discount', 0))}",
        f"🎁 За счёт кэшбэка: {_fmt_price(summary.get('cashback', 0))}",
        f"🚨 Поймано аномалий цен: {_fmt_price(summary.get('anomaly', 0))}",
        f"📊 Выгодных находок: {summary.get('actions', 0)}",
    ]
    if recent:
        lines.append("")
        lines.append("🕘 Последние находки:")
        kind_label = {"discount": "🏷 скидка", "cashback": "🎁 кэшбэк", "anomaly": "🚨 аномалия"}
        for s in recent[:5]:
            label = kind_label.get(s.kind, s.kind)
            lines.append(f"• {_fmt_price(s.amount)} — {label}: {s.product[:60]}")
    return "\n".join(lines)