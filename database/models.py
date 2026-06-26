"""
database/models.py — Schema definitions for all database tables.
Designed for easy migration to PostgreSQL.
"""

# ─── SQL Schema ───────────────────────────────────────────────────────────────
# Each CREATE TABLE statement is stored as a constant for clarity and reuse.

CREATE_CATEGORIES = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    emoji       TEXT DEFAULT '📦',
    position    INTEGER DEFAULT 0,
    is_active   INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id    INTEGER NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    price          REAL NOT NULL DEFAULT 0,
    emoji          TEXT DEFAULT '🛍️',
    thumbnail_url  TEXT DEFAULT '',
    banner_url     TEXT DEFAULT '',
    role_id        INTEGER DEFAULT 0,
    status         TEXT DEFAULT 'active',
    auto_restock   INTEGER DEFAULT 0,
    restock_amount INTEGER DEFAULT 0,
    min_stock      INTEGER DEFAULT 0,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);
"""

CREATE_STOCKS = """
CREATE TABLE IF NOT EXISTS stocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    variant_id  INTEGER DEFAULT 0,
    content     TEXT NOT NULL,
    is_sold     INTEGER DEFAULT 0,
    sold_at     TIMESTAMP,
    order_id    INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);
"""

CREATE_PAYMENTS = """
CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    details     TEXT DEFAULT '',
    is_active   INTEGER DEFAULT 1,
    position    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PRODUCT_PAYMENTS = """
CREATE TABLE IF NOT EXISTS product_payments (
    product_id  INTEGER NOT NULL,
    payment_id  INTEGER NOT NULL,
    PRIMARY KEY (product_id, payment_id),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (payment_id) REFERENCES payments(id) ON DELETE CASCADE
);
"""

CREATE_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    username        TEXT NOT NULL,
    product_id      INTEGER NOT NULL,
    product_name    TEXT NOT NULL,
    quantity        INTEGER DEFAULT 1,
    total_price     REAL NOT NULL,
    payment_method  TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    stock_content   TEXT DEFAULT '',
    ticket_channel  INTEGER DEFAULT 0,
    voucher_code    TEXT DEFAULT '',
    discount_amount REAL DEFAULT 0,
    invoice_number  TEXT UNIQUE,
    notes           TEXT DEFAULT '',
    variant_id      INTEGER DEFAULT 0,
    variant_name    TEXT DEFAULT '',
    payment_proof_url TEXT DEFAULT '',
    proof_submitted INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);
"""

CREATE_TICKETS = """
CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      INTEGER NOT NULL UNIQUE,
    user_id         INTEGER NOT NULL,
    username        TEXT NOT NULL,
    order_id        INTEGER,
    status          TEXT DEFAULT 'open',
    transcript_url  TEXT DEFAULT '',
    closed_by       INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at       TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

CREATE_VOUCHERS = """
CREATE TABLE IF NOT EXISTS vouchers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    description     TEXT DEFAULT '',
    discount_type   TEXT DEFAULT 'percent',
    discount_value  REAL NOT NULL,
    min_purchase    REAL DEFAULT 0,
    max_uses        INTEGER DEFAULT 0,
    used_count      INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_VOUCHER_USES = """
CREATE TABLE IF NOT EXISTS voucher_uses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_id  INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    order_id    INTEGER NOT NULL,
    used_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PURCHASE_HISTORY = """
CREATE TABLE IF NOT EXISTS purchase_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    username    TEXT NOT NULL,
    order_id    INTEGER NOT NULL,
    product_id  INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    total_price REAL NOT NULL,
    status      TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

CREATE_LOGS = """
CREATE TABLE IF NOT EXISTS activity_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    actor_id    INTEGER DEFAULT 0,
    actor_name  TEXT DEFAULT '',
    target      TEXT DEFAULT '',
    details     TEXT DEFAULT '',
    guild_id    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ─── All tables in creation order ─────────────────────────────────────────────
ALL_TABLES: list[str] = [
    CREATE_CATEGORIES,
    CREATE_PRODUCTS,
    CREATE_STOCKS,
    CREATE_PAYMENTS,
    CREATE_PRODUCT_PAYMENTS,
    CREATE_ORDERS,
    CREATE_TICKETS,
    CREATE_VOUCHERS,
    CREATE_VOUCHER_USES,
    CREATE_SETTINGS,
    CREATE_PURCHASE_HISTORY,
    CREATE_LOGS,
]

# ─── Default seed data ────────────────────────────────────────────────────────
DEFAULT_PAYMENTS: list[tuple[str, str, int]] = [
    ("Dana", "085xxxxxxxx (Dana)", 1),
    ("QRIS", "Scan QRIS yang dikirim admin", 2),
    ("OVO", "085xxxxxxxx (OVO)", 3),
    ("GoPay", "085xxxxxxxx (GoPay)", 4),
    ("ShopeePay", "085xxxxxxxx (ShopeePay)", 5),
    ("Bank Transfer", "BCA 1234567890 a.n. Store Owner", 6),
]

DEFAULT_SETTINGS: list[tuple[str, str]] = [
    ("store_name", "Premium Store"),
    ("store_description", "Temukan produk digital berkualitas!"),
    ("store_banner", ""),
    ("store_thumbnail", ""),
    ("store_color", "5865F2"),
    ("welcome_message", "Selamat datang di store kami!"),
    ("auto_close_ticket_hours", "24"),
    ("low_stock_threshold", "5"),
]

# ─── v2 Tables ────────────────────────────────────────────────────────────────

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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL UNIQUE,
    user_id      INTEGER NOT NULL,
    username     TEXT NOT NULL,
    product_id   INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    variant_name TEXT DEFAULT '',
    rating       INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    review       TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

# Append v2 tables to ALL_TABLES
ALL_TABLES.extend([CREATE_PRODUCT_VARIANTS, CREATE_RATINGS])

# Append v2 settings
DEFAULT_SETTINGS.extend([
    ("rating_channel_id", "0"),
])
