"""
database/migration_product_fields.py
Jalankan SEKALI setelah deploy untuk membuat tabel product_fields.

Usage:
    python database/migration_product_fields.py
"""

import sqlite3
import os
import sys

DB_PATH = os.getenv("DATABASE_PATH", "database/store.db")


def run() -> None:
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database tidak ditemukan: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── Tabel product_fields ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_fields (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL,
            label       TEXT    NOT NULL,
            placeholder TEXT    NOT NULL DEFAULT '',
            is_required INTEGER NOT NULL DEFAULT 1,
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_fields_product_id
        ON product_fields(product_id)
    """)

    conn.commit()
    conn.close()
    print("[OK] Tabel product_fields berhasil dibuat.")


if __name__ == "__main__":
    run()
