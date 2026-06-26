"""
database/database_v2_additions.py
Tambahkan method-method ini ke class Database yang ada di database/database.py
Copy paste semua method di bawah ke dalam class Database.
"""

# ─── TAMBAHKAN KE CLASS Database DI database/database.py ─────────────────────

# ─── Product Variants ─────────────────────────────────────────────────────────

async def get_product_variants(self, product_id: int) -> list:
    return await self._execute(
        "SELECT * FROM product_variants WHERE product_id = ? AND is_active = 1 ORDER BY position ASC, id ASC",
        (product_id,),
        fetch="all",
    ) or []

async def get_all_product_variants(self, product_id: int) -> list:
    return await self._execute(
        "SELECT * FROM product_variants WHERE product_id = ? ORDER BY position ASC, id ASC",
        (product_id,),
        fetch="all",
    ) or []

async def get_variant(self, variant_id: int):
    return await self._execute(
        "SELECT * FROM product_variants WHERE id = ?",
        (variant_id,),
        fetch="one",
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
        f"UPDATE product_variants SET {fields} WHERE id = ?",
        tuple(values),
    )

async def delete_variant(self, variant_id: int) -> int:
    return await self._execute(
        "DELETE FROM product_variants WHERE id = ?", (variant_id,)
    )

async def get_variant_stock_count(self, product_id: int, variant_id: int) -> int:
    """Count unsold stocks for a specific variant."""
    row = await self._execute(
        "SELECT COUNT(*) AS cnt FROM stocks WHERE product_id = ? AND variant_id = ? AND is_sold = 0",
        (product_id, variant_id),
        fetch="one",
    )
    return row["cnt"] if row else 0

async def get_next_variant_stock(self, product_id: int, variant_id: int):
    """FIFO: get oldest unsold stock for a specific variant."""
    return await self._execute(
        "SELECT * FROM stocks WHERE product_id = ? AND variant_id = ? AND is_sold = 0 ORDER BY id ASC LIMIT 1",
        (product_id, variant_id),
        fetch="one",
    )

async def add_variant_stocks(self, product_id: int, variant_id: int, contents: list) -> int:
    params = [(product_id, variant_id, c.strip()) for c in contents if c.strip()]
    await self._executemany(
        "INSERT INTO stocks (product_id, variant_id, content) VALUES (?, ?, ?)", params
    )
    return len(params)

# ─── Ratings ──────────────────────────────────────────────────────────────────

async def create_rating(
    self,
    order_id: int,
    user_id: int,
    username: str,
    product_id: int,
    product_name: str,
    variant_name: str,
    rating: int,
    review: str = "",
) -> int:
    return await self._execute(
        """
        INSERT INTO ratings
            (order_id, user_id, username, product_id, product_name, variant_name, rating, review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (order_id, user_id, username, product_id, product_name, variant_name, rating, review),
    )

async def get_rating_by_order(self, order_id: int):
    return await self._execute(
        "SELECT * FROM ratings WHERE order_id = ?", (order_id,), fetch="one"
    )

async def get_product_ratings(self, product_id: int, limit: int = 10) -> list:
    return await self._execute(
        "SELECT * FROM ratings WHERE product_id = ? ORDER BY created_at DESC LIMIT ?",
        (product_id, limit),
        fetch="all",
    ) or []

async def get_product_avg_rating(self, product_id: int) -> float:
    row = await self._execute(
        "SELECT AVG(rating) AS avg, COUNT(*) AS cnt FROM ratings WHERE product_id = ?",
        (product_id,),
        fetch="one",
    )
    return round(row["avg"] or 0, 1) if row else 0.0

async def get_recent_ratings(self, limit: int = 20) -> list:
    return await self._execute(
        "SELECT * FROM ratings ORDER BY created_at DESC LIMIT ?",
        (limit,),
        fetch="all",
    ) or []
