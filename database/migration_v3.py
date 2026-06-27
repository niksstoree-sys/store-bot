"""
database/migration_v3.py — Migration untuk fitur Required Fields.
Jalankan SEKALI setelah deploy v3: python database/migration_v3.py
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

CREATE_PRODUCT_FIELDS = """
CREATE TABLE IF NOT EXISTS product_fields (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    field_name  TEXT NOT NULL,
    field_label TEXT NOT NULL,
    placeholder TEXT DEFAULT '',
    is_required INTEGER DEFAULT 1,
    position    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);
"""

CREATE_ORDER_FIELD_VALUES = """
CREATE TABLE IF NOT EXISTS order_field_values (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL,
    field_name  TEXT NOT NULL,
    field_label TEXT NOT NULL,
    value       TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);
"""

def migrate():
    db_path = Config.DATABASE_PATH
    if not os.path.exists(db_path):
        print(f"❌ Database tidak ditemukan: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    print("🔄 Menjalankan migrasi v3 (Required Fields)...")

    cur.execute(CREATE_PRODUCT_FIELDS)
    print("  ✅ Tabel product_fields dibuat")

    cur.execute(CREATE_ORDER_FIELD_VALUES)
    print("  ✅ Tabel order_field_values dibuat")

    conn.commit()
    conn.close()
    print("\n✅ Migrasi v3 selesai!")
    print("\nLangkah selanjutnya:")
    print("  1. /sync di Discord")
    print("  2. /field preset product_id:1 preset:roblox")
    print("     (atau /field add untuk manual)")

if __name__ == "__main__":
    migrate()
