"""Асинхронный слой доступа к данным (SQLite через aiosqlite) и демо-хранилище в памяти."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

from .config import settings
from .models import Favorite, PriceHistory, PriceStat, SavingsEntry, SearchEntry, User

log = logging.getLogger(__name__)


class Database:
    """Работа с пользователями, избранным и историей цен."""

    def __init__(self) -> None:
        self.path: Optional[str] = None
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        url = settings.database_url
        if url.startswith("sqlite+aiosqlite:///"):
            self.path = url.split("///", 1)[1]
            parent = os.path.dirname(self.path) or "."
            os.makedirs(parent, exist_ok=True)
        else:
            # Любая другая схема пока приводится к локальному SQLite
            self.path = "data/bot.db"
            os.makedirs("data", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self._init_schema()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def _init_schema(self) -> None:
        assert self.conn is not None
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_premium INTEGER NOT NULL DEFAULT 0,
                daily_queries_used INTEGER NOT NULL DEFAULT 0,
                queries_date TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                market TEXT NOT NULL,
                product_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                last_price INTEGER NOT NULL DEFAULT 0,
                last_checked TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                favorite_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                checked_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS price_stats (
                market TEXT NOT NULL,
                product_id TEXT NOT NULL,
                last_price INTEGER,
                min_price INTEGER,
                max_price INTEGER,
                avg_price INTEGER,
                samples INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                PRIMARY KEY (market, product_id)
            );
            CREATE TABLE IF NOT EXISTS savings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                market TEXT NOT NULL,
                product TEXT NOT NULL DEFAULT '',
                amount INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_savings_user ON savings(user_id);
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                results_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_hist_user ON search_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_fav_user ON favorites(user_id);
            CREATE INDEX IF NOT EXISTS idx_hist_fav ON price_history(favorite_id);
            """
        )
        await self.conn.commit()

    # ---------- Пользователи ----------

    async def get_user(self, user_id: int) -> Optional[User]:
        assert self.conn is not None
        cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        return self._row_to_user(row) if row else None

    async def create_user(self, user_id: int, username: str = "", first_name: str = "") -> User:
        assert self.conn is not None
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name),
        )
        await self.conn.commit()
        return await self.get_user(user_id) or User(user_id=user_id, username=username, first_name=first_name)

    async def touch_user(
        self, user_id: int, username: str = "", first_name: str = ""
    ) -> None:
        """Обновить профиль и сбросить дневной счётчик, если наступил новый день."""
        assert self.conn is not None
        today = datetime.now().strftime("%Y-%m-%d")
        await self.conn.execute(
            """
            UPDATE users SET username = ?, first_name = ?,
                daily_queries_used = CASE WHEN queries_date = ? THEN daily_queries_used ELSE 0 END,
                queries_date = ?
            WHERE user_id = ?
            """,
            (username, first_name, today, today, user_id),
        )
        await self.conn.commit()

    async def inc_queries(self, user_id: int) -> None:
        assert self.conn is not None
        today = datetime.now().strftime("%Y-%m-%d")
        await self.conn.execute(
            """
            UPDATE users
            SET daily_queries_used = daily_queries_used + 1, queries_date = ?
            WHERE user_id = ? AND queries_date = ?
            """,
            (today, user_id, today),
        )
        await self.conn.commit()

    async def set_premium(self, user_id: int, is_premium: bool) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "UPDATE users SET is_premium = ? WHERE user_id = ?",
            (1 if is_premium else 0, user_id),
        )
        await self.conn.commit()

    @staticmethod
    def _row_to_user(row: aiosqlite.Row) -> User:
        return User(
            user_id=row["user_id"],
            username=row["username"] or "",
            first_name=row["first_name"] or "",
            is_premium=bool(row["is_premium"]),
            daily_queries_used=int(row["daily_queries_used"] or 0),
            queries_date=row["queries_date"] or "",
        )

    # ---------- Избранное ----------

    async def add_favorite(self, fav: Favorite) -> Favorite:
        assert self.conn is not None
        cur = await self.conn.execute(
            """
            INSERT INTO favorites (user_id, market, product_id, title, url, last_price, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fav.user_id, fav.market, fav.product_id, fav.title, fav.url, fav.last_price, datetime.now().isoformat()),
        )
        fav.id = cur.lastrowid
        await self.conn.commit()
        await cur.close()
        return fav

    async def list_favorites(self, user_id: int) -> list[Favorite]:
        assert self.conn is not None
        cur = await self.conn.execute(
            "SELECT * FROM favorites WHERE user_id = ? ORDER BY id DESC", (user_id,)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [self._row_to_fav(r) for r in rows]

    async def get_favorite(self, fav_id: int, user_id: int) -> Optional[Favorite]:
        assert self.conn is not None
        cur = await self.conn.execute(
            "SELECT * FROM favorites WHERE id = ? AND user_id = ?", (fav_id, user_id)
        )
        row = await cur.fetchone()
        await cur.close()
        return self._row_to_fav(row) if row else None

    async def delete_favorite(self, fav_id: int, user_id: int) -> bool:
        assert self.conn is not None
        cur = await self.conn.execute(
            "DELETE FROM favorites WHERE id = ? AND user_id = ?", (fav_id, user_id)
        )
        await self.conn.commit()
        deleted = cur.rowcount > 0
        await cur.close()
        return deleted

    async def update_favorite_price(self, fav_id: int, price: int) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "UPDATE favorites SET last_price = ?, last_checked = ? WHERE id = ?",
            (price, datetime.now().isoformat(), fav_id),
        )
        await self.conn.execute(
            "INSERT INTO price_history (favorite_id, price) VALUES (?, ?)",
            (fav_id, price),
        )
        await self.conn.commit()

    async def all_favorites(self) -> list[Favorite]:
        assert self.conn is not None
        cur = await self.conn.execute("SELECT * FROM favorites")
        rows = await cur.fetchall()
        await cur.close()
        return [self._row_to_fav(r) for r in rows]

    @staticmethod
    def _row_to_fav(row: aiosqlite.Row) -> Favorite:
        return Favorite(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            market=row["market"],
            product_id=row["product_id"],
            title=row["title"],
            url=row["url"] or "",
            last_price=int(row["last_price"] or 0),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    # ---------- Статистика цен (история наблюдений по товару) ----------

    async def record_price(self, market: str, product_id: str, price: int) -> None:
        """Записать наблюдение цены в price_stats (скользящая агрегация)."""
        assert self.conn is not None
        now = datetime.now().isoformat()
        await self.conn.execute(
            """
            INSERT INTO price_stats (market, product_id, last_price, min_price, max_price,
                                     avg_price, samples, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(market, product_id) DO UPDATE SET
                last_price = excluded.last_price,
                min_price = MIN(price_stats.min_price, excluded.min_price),
                max_price = MAX(price_stats.max_price, excluded.max_price),
                avg_price = (price_stats.avg_price * price_stats.samples + excluded.avg_price)
                            / (price_stats.samples + 1),
                samples = price_stats.samples + 1,
                last_seen = excluded.last_seen
            """,
            (market, product_id, price, price, price, price, now, now),
        )
        await self.conn.commit()

    async def get_price_stat(self, market: str, product_id: str) -> Optional[PriceStat]:
        assert self.conn is not None
        cur = await self.conn.execute(
            "SELECT * FROM price_stats WHERE market = ? AND product_id = ?",
            (market, product_id),
        )
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return None
        return PriceStat(
            market=row["market"],
            product_id=row["product_id"],
            last_price=row["last_price"],
            min_price=row["min_price"],
            max_price=row["max_price"],
            avg_price=row["avg_price"],
            samples=int(row["samples"] or 0),
            first_seen=datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
            last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
        )

    # ---------- Экономия ----------

    async def add_saving(
        self, user_id: int, market: str, product: str, amount: int, kind: str
    ) -> None:
        assert self.conn is not None
        if amount <= 0:
            return
        await self.conn.execute(
            "INSERT INTO savings (user_id, market, product, amount, kind) VALUES (?, ?, ?, ?, ?)",
            (user_id, market, product, amount, kind),
        )
        await self.conn.commit()

    async def get_savings_summary(self, user_id: int) -> dict[str, int]:
        """Сумма экономии по типам: total, discount, cashback, anomaly."""
        assert self.conn is not None
        cur = await self.conn.execute(
            "SELECT kind, SUM(amount) AS s, COUNT(*) AS c FROM savings WHERE user_id = ? GROUP BY kind",
            (user_id,),
        )
        rows = await cur.fetchall()
        await cur.close()
        summary: dict[str, int] = {"total": 0, "discount": 0, "cashback": 0, "anomaly": 0, "actions": 0}
        for row in rows:
            kind = row["kind"]
            s = int(row["s"] or 0)
            if kind in summary:
                summary[kind] += s
                summary["actions"] += int(row["c"] or 0)
        summary["total"] = sum(summary[k] for k in ("discount", "cashback", "anomaly"))
        return summary

    async def list_savings(self, user_id: int, limit: int = 10) -> list[SavingsEntry]:
        assert self.conn is not None
        cur = await self.conn.execute(
            "SELECT * FROM savings WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [self._row_to_saving(r) for r in rows]

    @staticmethod
    def _row_to_saving(row: aiosqlite.Row) -> SavingsEntry:
        return SavingsEntry(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            market=row["market"],
            product=row["product"] or "",
            amount=int(row["amount"] or 0),
            kind=row["kind"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )

    # ---------- История поиска ----------

    async def add_search(self, user_id: int, query: str, results_count: int = 0) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "INSERT INTO search_history (user_id, query, results_count) VALUES (?, ?, ?)",
            (user_id, query.strip()[:200], results_count),
        )
        await self.conn.commit()

    async def list_searches(self, user_id: int, limit: int = 10) -> list[SearchEntry]:
        assert self.conn is not None
        cur = await self.conn.execute(
            "SELECT * FROM search_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [self._row_to_search(r) for r in rows]

    async def clear_searches(self, user_id: int) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "DELETE FROM search_history WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()

    @staticmethod
    def _row_to_search(row: aiosqlite.Row) -> SearchEntry:
        return SearchEntry(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            query=row["query"] or "",
            results_count=int(row["results_count"] or 0),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        )


class DemoDatabase:
    """Хранилище в памяти с теми же методами — для запуска без файла БД."""

    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.favorites: dict[int, Favorite] = {}
        self._fav_seq = 0
        self._history: dict[int, list[PriceHistory]] = {}
        self._price_stats: dict[tuple[str, str], PriceStat] = {}
        self._savings: list[SavingsEntry] = []
        self._savings_seq = 0
        self._searches: list[SearchEntry] = []
        self._search_seq = 0

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    async def get_user(self, user_id: int) -> Optional[User]:
        u = self.users.get(user_id)
        if u and u.queries_date != self._today():
            u.daily_queries_used = 0
            u.queries_date = self._today()
        return u

    async def create_user(self, user_id: int, username: str = "", first_name: str = "") -> User:
        u = User(user_id=user_id, username=username, first_name=first_name, queries_date=self._today())
        self.users[user_id] = u
        return u

    async def touch_user(self, user_id: int, username: str = "", first_name: str = "") -> None:
        u = self.users.get(user_id) or await self.create_user(user_id, username, first_name)
        u.username, u.first_name = username, first_name
        if u.queries_date != self._today():
            u.daily_queries_used = 0
            u.queries_date = self._today()

    async def inc_queries(self, user_id: int) -> None:
        u = self.users.get(user_id)
        if u:
            if u.queries_date != self._today():
                u.daily_queries_used = 0
                u.queries_date = self._today()
            u.daily_queries_used += 1

    async def set_premium(self, user_id: int, is_premium: bool) -> None:
        u = self.users.get(user_id)
        if u:
            u.is_premium = is_premium

    async def add_favorite(self, fav: Favorite) -> Favorite:
        self._fav_seq += 1
        fav.id = self._fav_seq
        self.favorites[fav.id] = fav
        return fav

    async def list_favorites(self, user_id: int) -> list[Favorite]:
        return [f for f in self.favorites.values() if f.user_id == user_id]

    async def get_favorite(self, fav_id: int, user_id: int) -> Optional[Favorite]:
        f = self.favorites.get(fav_id)
        return f if f and f.user_id == user_id else None

    async def delete_favorite(self, fav_id: int, user_id: int) -> bool:
        f = self.favorites.get(fav_id)
        if f and f.user_id == user_id:
            del self.favorites[fav_id]
            return True
        return False

    async def update_favorite_price(self, fav_id: int, price: int) -> None:
        f = self.favorites.get(fav_id)
        if f:
            f.last_price = price
            self._history.setdefault(fav_id, []).append(PriceHistory(favorite_id=fav_id, price=price))

    async def all_favorites(self) -> list[Favorite]:
        return list(self.favorites.values())

    # ---------- Статистика цен (демо) ----------

    async def record_price(self, market: str, product_id: str, price: int) -> None:
        stat = self._price_stats.setdefault((market, product_id), PriceStat(market=market, product_id=product_id))
        now = datetime.now()
        if stat.samples == 0:
            stat.first_seen = now
        stat.samples += 1
        stat.last_price = price
        stat.last_seen = now
        stat.min_price = price if stat.min_price is None else min(stat.min_price, price)
        stat.max_price = price if stat.max_price is None else max(stat.max_price, price)
        stat.avg_price = (
            (stat.avg_price * (stat.samples - 1) + price) // stat.samples
            if stat.samples > 1 else price
        )

    async def get_price_stat(self, market: str, product_id: str) -> Optional[PriceStat]:
        return self._price_stats.get((market, product_id))

    # ---------- Экономия (демо) ----------

    async def add_saving(
        self, user_id: int, market: str, product: str, amount: int, kind: str
    ) -> None:
        if amount <= 0:
            return
        self._savings_seq += 1
        self._savings.append(
            SavingsEntry(
                id=self._savings_seq,
                user_id=user_id,
                market=market,
                product=product,
                amount=amount,
                kind=kind,
            )
        )

    async def get_savings_summary(self, user_id: int) -> dict[str, int]:
        summary: dict[str, int] = {"total": 0, "discount": 0, "cashback": 0, "anomaly": 0, "actions": 0}
        for s in self._savings:
            if s.user_id != user_id:
                continue
            if s.kind in summary:
                summary[s.kind] += s.amount
                summary["actions"] += 1
        summary["total"] = sum(summary[k] for k in ("discount", "cashback", "anomaly"))
        return summary

    async def list_savings(self, user_id: int, limit: int = 10) -> list[SavingsEntry]:
        return [s for s in self._savings if s.user_id == user_id][-limit:]

    # ---------- История поиска (демо) ----------

    async def add_search(self, user_id: int, query: str, results_count: int = 0) -> None:
        self._search_seq += 1
        self._searches.append(
            SearchEntry(
                id=self._search_seq,
                user_id=user_id,
                query=query.strip()[:200],
                results_count=results_count,
            )
        )

    async def list_searches(self, user_id: int, limit: int = 10) -> list[SearchEntry]:
        return [s for s in self._searches if s.user_id == user_id][-limit:]

    async def clear_searches(self, user_id: int) -> None:
        self._searches = [s for s in self._searches if s.user_id != user_id]


async def create_database() -> Database | DemoDatabase:
    db: Database | DemoDatabase
    if settings.database_url.startswith("memory") or settings.database_url.startswith("sqlite+aiosqlite:///:memory:"):
        db = DemoDatabase()
    else:
        db = Database()
    await db.connect()
    return db