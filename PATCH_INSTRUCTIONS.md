# 📦 Patch v2 — Cara Apply Update

## File yang Perlu Diupdate/Ditambah di Repo GitHub

---

## 1. File BARU — Upload ke GitHub

Upload file-file berikut ke repo lu:

### `database/migration_v2.py`
Script migrasi database. Jalankan SEKALI setelah deploy.

### `cogs/variant.py`
Cog baru untuk manajemen varian produk.

### `cogs/rating.py`
Cog baru untuk sistem rating & review.

---

## 2. File yang DIUPDATE

### `database/models.py`
Tambahkan di bagian `ALL_TABLES` (setelah `CREATE_LOGS`):

```python
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
```

Dan tambahkan ke list `ALL_TABLES`:
```python
ALL_TABLES: list[str] = [
    ...
    CREATE_PRODUCT_VARIANTS,  # tambahkan
    CREATE_RATINGS,           # tambahkan
]
```

Dan tambahkan ke `DEFAULT_SETTINGS`:
```python
DEFAULT_SETTINGS: list[tuple[str, str]] = [
    ...
    ("rating_channel_id", "0"),  # tambahkan
]
```

---

### `database/database.py`
Tambahkan method baru (dari file `database_v2_additions.py`) ke dalam class `Database`.

Juga update method `add_stocks` agar terima parameter `variant_id`:
```python
async def add_stocks(self, product_id: int, contents: list[str], variant_id: int = 0) -> int:
    params = [(product_id, variant_id, content.strip()) for content in contents if content.strip()]
    await self._executemany(
        "INSERT INTO stocks (product_id, variant_id, content) VALUES (?, ?, ?)", params
    )
    return len(params)
```

Dan update `CREATE_STOCKS` di `models.py` tambah kolom `variant_id`:
```sql
CREATE TABLE IF NOT EXISTS stocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    variant_id  INTEGER DEFAULT 0,
    content     TEXT NOT NULL,
    is_sold     INTEGER DEFAULT 0,
    ...
```

---

### `bot.py`
Tambahkan ke list `COGS`:
```python
COGS: list[str] = [
    ...
    "cogs.variant",   # tambahkan
    "cogs.rating",    # tambahkan
]
```

---

### `utils/views.py`
Tambahkan class-class baru dari `views_v2_additions.py`:
- `VariantSelectView`
- `VariantActionView`
- `VariantPaymentSelectView`
- `VariantOrderModal`
- `PaymentProofView`
- `PaymentProofModal`

Update `ProductActionView._buy_now` agar cek varian dulu:
```python
async def _buy_now(self, interaction: discord.Interaction) -> None:
    # Cek apakah produk punya varian
    variants = await self.db.get_product_variants(self.product["id"])
    if variants:
        # Arahkan ke variant select
        view = VariantSelectView(self.product, variants, self.payments, self.db)
        return await interaction.response.send_message(
            content="🎛️ Pilih tipe/varian produk:", view=view, ephemeral=True
        )
    # Tidak ada varian, langsung ke payment
    if not self.payments:
        from utils.embeds import error_embed
        return await interaction.response.send_message(
            embed=error_embed("Error", "Tidak ada metode pembayaran."), ephemeral=True
        )
    view = PaymentSelectView(self.product, self.payments, self.db)
    await interaction.response.send_message(
        content="💳 Pilih metode pembayaran:", view=view, ephemeral=True
    )
```

---

### `utils/ticket_welcome` di `utils/embeds.py`
Update `ticket_welcome_embed` agar tampilkan varian:
```python
def ticket_welcome_embed(user, order, product) -> discord.Embed:
    # Tambahkan variant_name jika ada
    variant_text = f" ({order['variant_name']})" if order.get('variant_name') else ""
    # dst...
```

---

### `cogs/order.py`

Tambahkan fungsi `process_purchase_variant`:
```python
async def process_purchase_variant(interaction, db, product, variant, payment, voucher_code="", notes=""):
    """Sama seperti process_purchase tapi untuk produk dengan varian."""
    # Override price dari variant
    # Gunakan variant_id untuk ambil stok
    # Simpan variant_name ke order
```

Update `confirm_order_in_ticket` agar cek `variant_id` dari order saat ambil stok.

---

### `cogs/ticket.py`
Update `ticket_welcome` message agar include tombol **Upload Bukti Pembayaran**:
```python
from utils.views import PaymentProofView, TicketActionView

proof_view = PaymentProofView(order_id, db)
# Kirim sebagai view terpisah atau gabung dengan TicketActionView
```

---

## 3. Setelah Push ke GitHub

1. Railway otomatis redeploy
2. Jalankan migration (Railway Console atau lokal):
   ```
   python database/migration_v2.py
   ```
3. Set channel rating di Discord:
   ```
   /rating set-channel #channel-rating
   ```
4. Sync commands:
   ```
   /sync
   ```

---

## 4. Command Baru

| Command | Keterangan |
|---------|------------|
| `/variant add` | Tambah varian ke produk |
| `/variant list` | Lihat varian produk |
| `/variant edit` | Edit varian |
| `/variant delete` | Hapus varian |
| `/variant stock-add` | Tambah stok per varian |
| `/rating set-channel` | Set channel rating |
| `/rating list` | Lihat rating produk |
| `/rating recent` | Rating terbaru semua produk |

---

## 5. Flow Baru

### Flow Beli dengan Varian:
```
User klik Buy Now
→ Bot tampilkan Select Varian (400 Robux / 800 Robux / dst)
→ User pilih varian
→ Bot tampilkan harga + stok varian
→ User klik Beli
→ Pilih payment
→ Ticket dibuat
→ Di ticket ada tombol "Upload Bukti Pembayaran"
→ User upload link screenshot
→ Bot kirim embed bukti ke ticket + ping admin
→ Admin verifikasi → Konfirmasi
→ Stok terkirim ke user via DM
→ Bot kirim tombol "Beri Rating" ke user
→ User beri rating 1-5 + review
→ Embed rating dikirim ke channel rating
```
