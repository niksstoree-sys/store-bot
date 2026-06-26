"""
database/database_fields_additions.py
──────────────────────────────────────
Salin method-method di bawah ini ke dalam class Database di database/database.py.
Letakkan di bagian manapun di dalam class, misalnya setelah method get_product.

JANGAN overwrite file database.py — cukup tambahkan method ini ke dalam class.
"""

# ─── PASTE KE DALAM class Database ───────────────────────────────────────────

    # ── Product Fields ────────────────────────────────────────────────────────

    async def get_product_fields(self, product_id: int) -> list:
        """Ambil semua custom field untuk sebuah produk, urut berdasarkan position."""
        return await self._execute(
            "SELECT * FROM product_fields WHERE product_id = ? ORDER BY position ASC",
            (product_id,),
            fetch="all",
        ) or []

    async def get_product_field(self, field_id: int):
        """Ambil satu field berdasarkan ID-nya."""
        return await self._execute(
            "SELECT * FROM product_fields WHERE id = ?",
            (field_id,),
            fetch="one",
        )

    async def add_product_field(
        self,
        product_id: int,
        label: str,
        placeholder: str = "",
        is_required: int = 1,
        position: int = 0,
    ) -> int:
        """Tambah custom field ke produk. Return ID field yang baru dibuat."""
        return await self._execute(
            """
            INSERT INTO product_fields (product_id, label, placeholder, is_required, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            (product_id, label, placeholder, is_required, position),
            fetch="lastrowid",
        )

    async def delete_product_field(self, field_id: int) -> None:
        """Hapus satu field berdasarkan ID."""
        await self._execute(
            "DELETE FROM product_fields WHERE id = ?",
            (field_id,),
        )

    async def clear_product_fields(self, product_id: int) -> None:
        """Hapus semua field untuk produk tertentu."""
        await self._execute(
            "DELETE FROM product_fields WHERE product_id = ?",
            (product_id,),
        )
