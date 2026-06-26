"""
database/database.py — Async SQLite database manager.
All queries use parameterized inputs to prevent SQL injection.
Designed with PostgreSQL migration in mind (no SQLite-specific syntax in queries).
"""

import sqlite3
import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Optional
from contextlib import asynccontextmanager

from database.models import ALL_TABLES, DEFAULT_PAYMENTS, DEFAULT_SETTINGS

logger = logging.getLogger("store.database")


class Database:
    """
    Async-compatible SQLite database manager.
    Uses a thread-pool executor to run blocking sqlite3 calls without
    blocking the Discord event loop.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()

    # ─── Internal Helpers ─────────────────────────────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    async def _execute(
        self,
        query: str,
        params: tuple = (),
        fetch: str = "none",
    ) -> Any:
        """
        Execute a query on a thread-pool executor.
        fetch: 'one' | 'all' | 'none'
        Returns lastrowid for INSERT, rowcount for UPDATE/DELETE, or rows.
        """
        loop = asyncio.get_event_loop()

        def _run() -> Any:
            with self._get_connection() as conn:
                cur = conn.execute(query, params)
                if fetch == "one":
                    return cur.fetchone()
                elif fetch == "all":
                    return cur.fetchall()
                else:
                    conn.commit()
                    return cur.lastrowid if query.strip().upper().startswith("INSERT") else cur.rowcount

        async with self._lock:
            return await loop.run_in_executor(None, _run)

    async def _executemany(self, query: str, params_list: list[tuple]) -> None:
        loop = asyncio.get_event_loop()

        def _run() -> None:
            with self._get_connection() as conn:
                conn.executemany(query, params_list)
                conn.commit()

        async with self._lock:
            await loop.run_in_executor(None, _run)

    # ─── Initialisation ───────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create all tables and seed default data."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        for table_sql in ALL_TABLES:
            await self._execute(table_sql)

        await self._seed_defaults()
        logger.info("Database initialized successfully.")

    async def _seed_defaults(self) -> None:
        """Insert default payments and settings if not present."""
        for name, details, position in DEFAULT_PAYMENTS:
            existing = await self._execute(
                "SELECT id FROM payments WHERE name = ?", (name,), fetch="one"
            )
            if not existing:
                await self._execute(
                    "INSERT INTO payments (name, details, position) VALUES (?, ?, ?)",
                    (name, details, position),
                )

        for key, value in DEFAULT_SETTINGS:
            existing = await self._execute(
                "SELECT key FROM settings WHERE key = ?", (key,), fetch="one"
            )
            if not existing:
                await self._execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", (key, value)
                )

    # ─── Settings ─────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        row = await self._execute(
            "SELECT value FROM settings WHERE key = ?", (key,), fetch="one"
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value),
        )

    async def get_all_settings(self) -> dict[str, str]:
        rows = await self._execute("SELECT key, value FROM settings", fetch="all")
        return {row["key"]: row["value"] for row in rows} if rows else {}

    # ─── Categories ───────────────────────────────────────────────────────────

    async def get_categories(self, active_only: bool = False) -> list[sqlite3.Row]:
        query = "SELECT * FROM categories"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY position ASC, id ASC"
        return await self._execute(query, fetch="all") or []

    async def get_category(self, category_id: int) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,), fetch="one"
        )

    async def get_category_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM categories WHERE LOWER(name) = LOWER(?)", (name,), fetch="one"
        )

    async def create_category(
        self,
        name: str,
        description: str = "",
        emoji: str = "📦",
        position: int = 0,
    ) -> int:
        return await self._execute(
            "INSERT INTO categories (name, description, emoji, position) VALUES (?, ?, ?, ?)",
            (name, description, emoji, position),
        )

    async def update_category(self, category_id: int, **kwargs: Any) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [category_id]
        return await self._execute(
            f"UPDATE categories SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )

    async def delete_category(self, category_id: int) -> int:
        return await self._execute(
            "DELETE FROM categories WHERE id = ?", (category_id,)
        )

    # ─── Products ─────────────────────────────────────────────────────────────

    async def get_products(
        self, category_id: Optional[int] = None, active_only: bool = False
    ) -> list[sqlite3.Row]:
        query = "SELECT p.*, c.name AS category_name FROM products p JOIN categories c ON p.category_id = c.id"
        conditions = []
        params: list[Any] = []
        if category_id is not None:
            conditions.append("p.category_id = ?")
            params.append(category_id)
        if active_only:
            conditions.append("p.status = 'active'")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY p.name ASC"
        return await self._execute(query, tuple(params), fetch="all") or []

    async def get_product(self, product_id: int) -> Optional[sqlite3.Row]:
        return await self._execute(
            """
            SELECT p.*, c.name AS category_name
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.id = ?
            """,
            (product_id,),
            fetch="one",
        )

    async def create_product(
        self,
        category_id: int,
        name: str,
        description: str,
        price: float,
        emoji: str = "🛍️",
        thumbnail_url: str = "",
        banner_url: str = "",
        role_id: int = 0,
    ) -> int:
        return await self._execute(
            """
            INSERT INTO products
                (category_id, name, description, price, emoji, thumbnail_url, banner_url, role_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (category_id, name, description, price, emoji, thumbnail_url, banner_url, role_id),
        )

    async def update_product(self, product_id: int, **kwargs: Any) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [product_id]
        return await self._execute(
            f"UPDATE products SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )

    async def delete_product(self, product_id: int) -> int:
        return await self._execute("DELETE FROM products WHERE id = ?", (product_id,))

    async def get_product_stock_count(self, product_id: int) -> int:
        row = await self._execute(
            "SELECT COUNT(*) AS cnt FROM stocks WHERE product_id = ? AND is_sold = 0",
            (product_id,),
            fetch="one",
        )
        return row["cnt"] if row else 0

    async def search_products(self, query: str) -> list[sqlite3.Row]:
        pattern = f"%{query}%"
        return await self._execute(
            """
            SELECT p.*, c.name AS category_name
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.status = 'active' AND (p.name LIKE ? OR p.description LIKE ?)
            ORDER BY p.name ASC
            """,
            (pattern, pattern),
            fetch="all",
        ) or []

    async def get_top_selling_products(self, limit: int = 5) -> list[sqlite3.Row]:
        return await self._execute(
            """
            SELECT p.id, p.name, p.price, COUNT(o.id) AS total_orders,
                   SUM(o.total_price) AS total_revenue
            FROM products p
            LEFT JOIN orders o ON p.id = o.product_id AND o.status = 'success'
            GROUP BY p.id
            ORDER BY total_orders DESC
            LIMIT ?
            """,
            (limit,),
            fetch="all",
        ) or []

    # ─── Stocks ───────────────────────────────────────────────────────────────

    async def add_stocks(self, product_id: int, contents: list[str], variant_id: int = 0) -> int:
        params = [(product_id, variant_id, content.strip()) for content in contents if content.strip()]
        await self._executemany(
            "INSERT INTO stocks (product_id, variant_id, content) VALUES (?, ?, ?)", params
        )
        return len(params)

    async def get_next_stock(self, product_id: int, variant_id: int = 0):
        """FIFO: get oldest unsold stock. If variant_id > 0, filter by variant."""
        if variant_id > 0:
            return await self._execute(
                "SELECT * FROM stocks WHERE product_id = ? AND variant_id = ? AND is_sold = 0 ORDER BY id ASC LIMIT 1",
                (product_id, variant_id),
                fetch="one",
            )
        return await self._execute(
            "SELECT * FROM stocks WHERE product_id = ? AND is_sold = 0 ORDER BY id ASC LIMIT 1",
            (product_id,),
            fetch="one",
        )

    async def get_stock_count_by_variant(self, product_id: int, variant_id: int) -> int:
        row = await self._execute(
            "SELECT COUNT(*) AS cnt FROM stocks WHERE product_id = ? AND variant_id = ? AND is_sold = 0",
            (product_id, variant_id),
            fetch="one",
        )
        return row["cnt"] if row else 0


    async def mark_stock_sold(self, stock_id: int, order_id: int) -> None:
        await self._execute(
            "UPDATE stocks SET is_sold = 1, sold_at = CURRENT_TIMESTAMP, order_id = ? WHERE id = ?",
            (order_id, stock_id),
        )

    async def remove_stock(self, stock_id: int) -> int:
        return await self._execute("DELETE FROM stocks WHERE id = ?", (stock_id,))

    async def get_stocks(self, product_id: int, sold: bool = False) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM stocks WHERE product_id = ? AND is_sold = ? ORDER BY id ASC",
            (product_id, 1 if sold else 0),
            fetch="all",
        ) or []

    # ─── Payments ─────────────────────────────────────────────────────────────

    async def get_payments(self, active_only: bool = False) -> list[sqlite3.Row]:
        query = "SELECT * FROM payments"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY position ASC"
        return await self._execute(query, fetch="all") or []

    async def get_payment(self, payment_id: int) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,), fetch="one"
        )

    async def get_payment_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM payments WHERE LOWER(name) = LOWER(?)", (name,), fetch="one"
        )

    async def create_payment(self, name: str, details: str, position: int = 0) -> int:
        return await self._execute(
            "INSERT INTO payments (name, details, position) VALUES (?, ?, ?)",
            (name, details, position),
        )

    async def update_payment(self, payment_id: int, **kwargs: Any) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [payment_id]
        return await self._execute(
            f"UPDATE payments SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )

    async def delete_payment(self, payment_id: int) -> int:
        return await self._execute("DELETE FROM payments WHERE id = ?", (payment_id,))

    async def get_product_payments(self, product_id: int) -> list[sqlite3.Row]:
        return await self._execute(
            """
            SELECT p.* FROM payments p
            JOIN product_payments pp ON p.id = pp.payment_id
            WHERE pp.product_id = ? AND p.is_active = 1
            ORDER BY p.position ASC
            """,
            (product_id,),
            fetch="all",
        ) or []

    async def set_product_payments(self, product_id: int, payment_ids: list[int]) -> None:
        await self._execute(
            "DELETE FROM product_payments WHERE product_id = ?", (product_id,)
        )
        if payment_ids:
            params = [(product_id, pid) for pid in payment_ids]
            await self._executemany(
                "INSERT INTO product_payments (product_id, payment_id) VALUES (?, ?)", params
            )

    # ─── Orders ───────────────────────────────────────────────────────────────

    async def create_order(
        self,
        user_id: int,
        username: str,
        product_id: int,
        product_name: str,
        total_price: float,
        payment_method: str,
        quantity: int = 1,
        voucher_code: str = "",
        discount_amount: float = 0.0,
        notes: str = "",
    ) -> int:
        invoice = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id % 1000:03d}"
        return await self._execute(
            """
            INSERT INTO orders
                (user_id, username, product_id, product_name, quantity, total_price,
                 payment_method, invoice_number, voucher_code, discount_amount, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, username, product_id, product_name, quantity,
                total_price, payment_method, invoice, voucher_code,
                discount_amount, notes,
            ),
        )

    async def get_order(self, order_id: int) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,), fetch="one"
        )

    async def get_order_by_invoice(self, invoice: str) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM orders WHERE invoice_number = ?", (invoice,), fetch="one"
        )

    async def update_order(self, order_id: int, **kwargs: Any) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [order_id]
        return await self._execute(
            f"UPDATE orders SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )

    async def get_user_orders(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
            fetch="all",
        ) or []

    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM orders"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self._execute(query, tuple(params), fetch="all") or []

    async def get_order_stats(self) -> dict[str, Any]:
        total = await self._execute(
            "SELECT COUNT(*) AS cnt FROM orders", fetch="one"
        )
        success = await self._execute(
            "SELECT COUNT(*) AS cnt, SUM(total_price) AS revenue FROM orders WHERE status = 'success'",
            fetch="one",
        )
        pending = await self._execute(
            "SELECT COUNT(*) AS cnt FROM orders WHERE status = 'pending'", fetch="one"
        )
        unique_buyers = await self._execute(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM orders WHERE status = 'success'",
            fetch="one",
        )
        return {
            "total": total["cnt"] if total else 0,
            "success": success["cnt"] if success else 0,
            "revenue": success["revenue"] if success and success["revenue"] else 0.0,
            "pending": pending["cnt"] if pending else 0,
            "unique_buyers": unique_buyers["cnt"] if unique_buyers else 0,
        }

    async def get_top_customers(self, limit: int = 5) -> list[sqlite3.Row]:
        return await self._execute(
            """
            SELECT user_id, username,
                   COUNT(*) AS total_orders,
                   SUM(total_price) AS total_spent
            FROM orders
            WHERE status = 'success'
            GROUP BY user_id
            ORDER BY total_spent DESC
            LIMIT ?
            """,
            (limit,),
            fetch="all",
        ) or []

    # ─── Tickets ──────────────────────────────────────────────────────────────

    async def create_ticket(
        self,
        channel_id: int,
        user_id: int,
        username: str,
        order_id: Optional[int] = None,
    ) -> int:
        return await self._execute(
            "INSERT INTO tickets (channel_id, user_id, username, order_id) VALUES (?, ?, ?, ?)",
            (channel_id, user_id, username, order_id),
        )

    async def get_ticket(self, ticket_id: int) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,), fetch="one"
        )

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,), fetch="one"
        )

    async def get_user_tickets(self, user_id: int) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
            fetch="all",
        ) or []

    async def update_ticket(self, ticket_id: int, **kwargs: Any) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [ticket_id]
        return await self._execute(
            f"UPDATE tickets SET {fields} WHERE id = ?", tuple(values)
        )

    async def get_ticket_stats(self) -> dict[str, Any]:
        total = await self._execute(
            "SELECT COUNT(*) AS cnt FROM tickets", fetch="one"
        )
        open_t = await self._execute(
            "SELECT COUNT(*) AS cnt FROM tickets WHERE status = 'open'", fetch="one"
        )
        closed_t = await self._execute(
            "SELECT COUNT(*) AS cnt FROM tickets WHERE status = 'closed'", fetch="one"
        )
        return {
            "total": total["cnt"] if total else 0,
            "open": open_t["cnt"] if open_t else 0,
            "closed": closed_t["cnt"] if closed_t else 0,
        }

    # ─── Vouchers ─────────────────────────────────────────────────────────────

    async def get_voucher(self, code: str) -> Optional[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM vouchers WHERE UPPER(code) = UPPER(?) AND is_active = 1",
            (code,),
            fetch="one",
        )

    async def get_all_vouchers(self) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM vouchers ORDER BY created_at DESC", fetch="all"
        ) or []

    async def create_voucher(
        self,
        code: str,
        description: str,
        discount_type: str,
        discount_value: float,
        min_purchase: float = 0,
        max_uses: int = 0,
        expires_at: Optional[str] = None,
    ) -> int:
        return await self._execute(
            """
            INSERT INTO vouchers
                (code, description, discount_type, discount_value, min_purchase, max_uses, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (code, description, discount_type, discount_value, min_purchase, max_uses, expires_at),
        )

    async def use_voucher(self, voucher_id: int, user_id: int, order_id: int) -> None:
        await self._execute(
            "UPDATE vouchers SET used_count = used_count + 1 WHERE id = ?", (voucher_id,)
        )
        await self._execute(
            "INSERT INTO voucher_uses (voucher_id, user_id, order_id) VALUES (?, ?, ?)",
            (voucher_id, user_id, order_id),
        )

    async def user_used_voucher(self, voucher_id: int, user_id: int) -> bool:
        row = await self._execute(
            "SELECT id FROM voucher_uses WHERE voucher_id = ? AND user_id = ?",
            (voucher_id, user_id),
            fetch="one",
        )
        return row is not None

    async def update_voucher(self, voucher_id: int, **kwargs: Any) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [voucher_id]
        return await self._execute(
            f"UPDATE vouchers SET {fields} WHERE id = ?", tuple(values)
        )

    async def delete_voucher(self, voucher_id: int) -> int:
        return await self._execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))

    # ─── Activity Logs ────────────────────────────────────────────────────────

    async def log_activity(
        self,
        action: str,
        actor_id: int = 0,
        actor_name: str = "",
        target: str = "",
        details: str = "",
        guild_id: int = 0,
    ) -> None:
        await self._execute(
            """
            INSERT INTO activity_logs (action, actor_id, actor_name, target, details, guild_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, actor_id, actor_name, target, details, guild_id),
        )

    async def get_recent_logs(self, limit: int = 50) -> list[sqlite3.Row]:
        return await self._execute(
            "SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
            fetch="all",
        ) or []

    # ─── Purchase History ─────────────────────────────────────────────────────

    async def add_purchase_history(
        self,
        user_id: int,
        username: str,
        order_id: int,
        product_id: int,
        product_name: str,
        total_price: float,
        status: str,
    ) -> None:
        await self._execute(
            """
            INSERT INTO purchase_history
                (user_id, username, order_id, product_id, product_name, total_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, order_id, product_id, product_name, total_price, status),
        )

    async def get_user_purchase_history(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> list[sqlite3.Row]:
        return await self._execute(
            """
            SELECT * FROM purchase_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
            fetch="all",
        ) or []

    # ─── Stats ────────────────────────────────────────────────────────────────

    async def get_full_stats(self) -> dict[str, Any]:
        cat_count = await self._execute(
            "SELECT COUNT(*) AS cnt FROM categories WHERE is_active = 1", fetch="one"
        )
        prod_count = await self._execute(
            "SELECT COUNT(*) AS cnt FROM products WHERE status = 'active'", fetch="one"
        )
        stock_count = await self._execute(
            "SELECT COUNT(*) AS cnt FROM stocks WHERE is_sold = 0", fetch="one"
        )
        order_stats = await self.get_order_stats()
        ticket_stats = await self.get_ticket_stats()

        return {
            "categories": cat_count["cnt"] if cat_count else 0,
            "products": prod_count["cnt"] if prod_count else 0,
            "available_stock": stock_count["cnt"] if stock_count else 0,
            **order_stats,
            **{f"ticket_{k}": v for k, v in ticket_stats.items()},
        }

    # ─── Product Variants ─────────────────────────────────────────────────────

    async def get_product_variants(self, product_id: int) -> list:
        return await self._execute(
            "SELECT * FROM product_variants WHERE product_id = ? AND is_active = 1 ORDER BY position ASC, id ASC",
            (product_id,), fetch="all",
        ) or []

    async def get_all_product_variants(self, product_id: int) -> list:
        return await self._execute(
            "SELECT * FROM product_variants WHERE product_id = ? ORDER BY position ASC, id ASC",
            (product_id,), fetch="all",
        ) or []

    async def get_variant(self, variant_id: int):
        return await self._execute(
            "SELECT * FROM product_variants WHERE id = ?", (variant_id,), fetch="one"
        )

    async def create_variant(self, product_id: int, name: str, price: float, position: int = 0) -> int:
        return await self._execute(
            "INSERT INTO product_variants (product_id, name, price, position) VALUES (?, ?, ?, ?)",
            (product_id, name, price, position),
        )

    async def update_variant(self, variant_id: int, **kwargs) -> int:
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [variant_id]
        return await self._execute(
            f"UPDATE product_variants SET {fields} WHERE id = ?", tuple(values)
        )

    async def delete_variant(self, variant_id: int) -> int:
        return await self._execute("DELETE FROM product_variants WHERE id = ?", (variant_id,))

    # ─── Ratings ──────────────────────────────────────────────────────────────

    async def create_rating(
        self, order_id: int, user_id: int, username: str,
        product_id: int, product_name: str, variant_name: str,
        rating: int, review: str = "",
    ) -> int:
        return await self._execute(
            """INSERT INTO ratings
               (order_id, user_id, username, product_id, product_name, variant_name, rating, review)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, user_id, username, product_id, product_name, variant_name, rating, review),
        )

    async def get_rating_by_order(self, order_id: int):
        return await self._execute(
            "SELECT * FROM ratings WHERE order_id = ?", (order_id,), fetch="one"
        )

    async def get_product_ratings(self, product_id: int, limit: int = 10) -> list:
        return await self._execute(
            "SELECT * FROM ratings WHERE product_id = ? ORDER BY created_at DESC LIMIT ?",
            (product_id, limit), fetch="all",
        ) or []

    async def get_product_avg_rating(self, product_id: int) -> float:
        row = await self._execute(
            "SELECT AVG(rating) AS avg, COUNT(*) AS cnt FROM ratings WHERE product_id = ?",
            (product_id,), fetch="one",
        )
        return round(row["avg"] or 0, 1) if row else 0.0

    async def get_recent_ratings(self, limit: int = 20) -> list:
        return await self._execute(
            "SELECT * FROM ratings ORDER BY created_at DESC LIMIT ?", (limit,), fetch="all",
        ) or []
