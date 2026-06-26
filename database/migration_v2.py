"""
database/migration_v2.py — Migration script untuk menambah tabel baru.
Jalankan sekali: python database/migration_v2.py
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

CREATE_PRODUCT_VARIANTS = """
CREATE TABLE IF NOT EXISTS product_variants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    name        TEXT NOT NULL,
    price       REAL NOT NULL DEFAULT 0,
    is_active   INTEGER DEFAULT 1,
    position    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);
"""

CREATE_RATINGS = """
CREATE TABLE IF NOT EXISTS ratings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    username    TEXT NOT NULL,
    product_id  INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    variant_name TEXT DEFAULT '',
    rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    review      TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

ALTER_ORDERS_VARIANT = """
ALTER TABLE orders ADD COLUMN variant_id INTEGER DEFAULT 0;
"""

ALTER_ORDERS_VARIANT_NAME = """
ALTER TABLE orders ADD COLUMN variant_name TEXT DEFAULT '';
"""

ALTER_ORDERS_PROOF = """
ALTER TABLE orders ADD COLUMN payment_proof_url TEXT DEFAULT '';
"""

ALTER_ORDERS_PROOF_STATUS = """
ALTER TABLE orders ADD COLUMN proof_submitted INTEGER DEFAULT 0;
"""

ALTER_SETTINGS_RATING = """
INSERT OR IGNORE INTO settings (key, value) VALUES ('rating_channel_id', '0');
"""

def migrate():
    db_path = Config.DATABASE_PATH
    if not os.path.exists(db_path):
        print(f"❌ Database tidak ditemukan di: {db_path}")
        print("Pastikan bot sudah pernah dijalankan minimal sekali.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("🔄 Menjalankan migrasi v2...")

    # Create new tables
    cur.execute(CREATE_PRODUCT_VARIANTS)
    print("  ✅ Tabel product_variants dibuat")

    cur.execute(CREATE_RATINGS)
    print("  ✅ Tabel ratings dibuat")

    # Alter orders table (ignore if column already exists)
    for sql, col in [
        (ALTER_ORDERS_VARIANT, "variant_id"),
        (ALTER_ORDERS_VARIANT_NAME, "variant_name"),
        (ALTER_ORDERS_PROOF, "payment_proof_url"),
        (ALTER_ORDERS_PROOF_STATUS, "proof_submitted"),
    ]:
        try:
            cur.execute(sql)
            print(f"  ✅ Kolom {col} ditambahkan ke orders")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  ⏭️  Kolom {col} sudah ada, skip")
            else:
                print(f"  ⚠️  {e}")

    # Insert default settings
    cur.execute(ALTER_SETTINGS_RATING)
    print("  ✅ Setting rating_channel_id ditambahkan")

    conn.commit()
    conn.close()
    print("\n✅ Migrasi v2 selesai!")

if __name__ == "__main__":
    migrate()
