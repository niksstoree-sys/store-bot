"""
utils/views.py — All Discord UI components: Views, Buttons, Selects, Modals.
All store-critical Views are Persistent (custom_id based) so they survive bot restarts.
"""

import logging
from typing import Optional, TYPE_CHECKING

import discord
from discord import ui

from config import Config
from utils.helpers import is_admin, format_price

if TYPE_CHECKING:
    from database.database import Database

logger = logging.getLogger("store.views")


# ─── Simple Confirm View ──────────────────────────────────────────────────────

class ConfirmView(ui.View):
    """Generic Yes/No confirmation view (ephemeral, non-persistent)."""

    def __init__(self, author_id: int, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.confirmed: bool = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Bukan interaksi kamu.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="✅ Ya", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @ui.button(label="❌ Tidak", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.confirmed = False
        self.stop()
        await interaction.response.defer()


# ─── Pagination View ──────────────────────────────────────────────────────────

class PaginationView(ui.View):
    """Generic paginator. Subclass and override get_embed_for_page."""

    def __init__(self, author_id: int, total_pages: int, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.total_pages = total_pages
        self.current_page = 1
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current_page <= 1
        self.next_btn.disabled = self.current_page >= self.total_pages

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Bukan interaksi kamu.", ephemeral=True)
            return False
        return True

    async def get_embed_for_page(self, page: int) -> discord.Embed:
        raise NotImplementedError

    @ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.current_page = max(1, self.current_page - 1)
        self._update_buttons()
        embed = await self.get_embed_for_page(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.current_page = min(self.total_pages, self.current_page + 1)
        self._update_buttons()
        embed = await self.get_embed_for_page(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)


# ─── Store Main View (Persistent) ─────────────────────────────────────────────

class StoreCategorySelect(ui.Select):
    def __init__(self, categories: list, db: "Database") -> None:
        self.db = db
        options = [
            discord.SelectOption(
                label=cat["name"],
                value=str(cat["id"]),
                description=cat["description"][:100] if cat["description"] else None,
                emoji=cat["emoji"] if cat["emoji"] else "📦",
            )
            for cat in categories[:25]  # Discord max 25 options
        ]
        if not options:
            options = [discord.SelectOption(label="Tidak ada kategori", value="0")]

        super().__init__(
            placeholder="📂 Pilih Kategori...",
            options=options,
            custom_id="store:category_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from utils.embeds import error_embed

        category_id = int(self.values[0])
        if category_id == 0:
            return await interaction.response.send_message(
                embed=error_embed("Tidak Ada Kategori", "Belum ada kategori yang tersedia."),
                ephemeral=True,
            )

        category = await self.db.get_category(category_id)
        if not category:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Kategori tidak ditemukan."), ephemeral=True
            )

        products = await self.db.get_products(category_id=category_id, active_only=True)
        if not products:
            from utils.embeds import info_embed
            return await interaction.response.send_message(
                embed=info_embed("Kosong", f"Belum ada produk di kategori **{category['name']}**."),
                ephemeral=True,
            )

        view = ProductSelectView(products, self.db)
        await interaction.response.send_message(
            content=f"📂 **{category['emoji']} {category['name']}** — Pilih produk:",
            view=view,
            ephemeral=True,
        )


class StoreMainView(ui.View):
    """Persistent store view with category select menu."""

    def __init__(self, categories: list, db: "Database") -> None:
        super().__init__(timeout=None)
        self.add_item(StoreCategorySelect(categories, db))


# ─── Product Select View ──────────────────────────────────────────────────────

class ProductSelectView(ui.View):
    def __init__(self, products: list, db: "Database") -> None:
        super().__init__(timeout=180)
        self.db = db

        options = [
            discord.SelectOption(
                label=p["name"][:100],
                value=str(p["id"]),
                emoji=p["emoji"] if p["emoji"] else "🛍️",
                description=f"{format_price(p['price'])}",
            )
            for p in products[:25]
        ]
        select = ui.Select(
            placeholder="🛍️ Pilih Produk...",
            options=options,
            custom_id="store:product_select",
        )
        select.callback = self._product_selected
        self.add_item(select)

    async def _product_selected(self, interaction: discord.Interaction) -> None:
        from utils.embeds import product_embed, error_embed

        product_id = int(interaction.data["values"][0])
        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Produk tidak ditemukan."), ephemeral=True
            )

        stock_count = await self.db.get_product_stock_count(product_id)
        payments = await self.db.get_product_payments(product_id)

        embed = product_embed(product, stock_count, payments)
        view = ProductActionView(product, stock_count, payments, self.db)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ─── Product Action View ──────────────────────────────────────────────────────

class ProductActionView(ui.View):
    """View shown after user selects a product. Contains Buy Now + Refresh."""

    def __init__(
        self,
        product,
        stock_count: int,
        payments: list,
        db: "Database",
    ) -> None:
        super().__init__(timeout=180)
        self.product = product
        self.db = db
        self.payments = payments

        buy_btn = ui.Button(
            label="🛒 Beli Sekarang",
            style=discord.ButtonStyle.success,
            disabled=stock_count == 0,
            custom_id=f"product:buy:{product['id']}",
        )
        buy_btn.callback = self._buy_now
        self.add_item(buy_btn)

        refresh_btn = ui.Button(
            label="🔄 Refresh Stok",
            style=discord.ButtonStyle.secondary,
            custom_id=f"product:refresh:{product['id']}",
        )
        refresh_btn.callback = self._refresh
        self.add_item(refresh_btn)

    async def _buy_now(self, interaction: discord.Interaction) -> None:
        from utils.embeds import error_embed

        # Cek apakah produk punya varian
        variants = await self.db.get_product_variants(self.product["id"])
        if variants:
            view = VariantSelectView(self.product, variants, self.payments, self.db)
            return await interaction.response.send_message(
                content="🎛️ Pilih tipe/varian produk:",
                view=view,
                ephemeral=True,
            )

        if not self.payments:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Tidak ada metode pembayaran tersedia."),
                ephemeral=True,
            )
        view = PaymentSelectView(self.product, self.payments, self.db)
        await interaction.response.send_message(
            content="💳 Pilih metode pembayaran:",
            view=view,
            ephemeral=True,
        )

    async def _refresh(self, interaction: discord.Interaction) -> None:
        from utils.embeds import product_embed

        stock_count = await self.db.get_product_stock_count(self.product["id"])
        payments = await self.db.get_product_payments(self.product["id"])
        embed = product_embed(self.product, stock_count, payments)
        view = ProductActionView(self.product, stock_count, payments, self.db)
        await interaction.response.edit_message(embed=embed, view=view)


# ─── Payment Select View ──────────────────────────────────────────────────────

class PaymentSelectView(ui.View):
    def __init__(self, product, payments: list, db: "Database") -> None:
        super().__init__(timeout=120)
        self.product = product
        self.db = db

        options = [
            discord.SelectOption(label=p["name"], value=str(p["id"]))
            for p in payments[:25]
        ]
        select = ui.Select(
            placeholder="💳 Pilih Metode Pembayaran...",
            options=options,
        )
        select.callback = self._payment_selected
        self.add_item(select)

    async def _payment_selected(self, interaction: discord.Interaction) -> None:
        payment_id = int(interaction.data["values"][0])
        payment = await self.db.get_payment(payment_id)
        if not payment:
            from utils.embeds import error_embed
            return await interaction.response.send_message(
                embed=error_embed("Error", "Metode pembayaran tidak ditemukan."), ephemeral=True
            )
        # Cek apakah produk ini punya custom fields
        fields = await self.db.get_product_fields(self.product["id"])
        if fields:
            modal = DynamicOrderModal(self.product, payment, self.db, fields, variant=None)
        else:
            modal = OrderNoteModal(self.product, payment, self.db)
        await interaction.response.send_modal(modal)


# ─── Order Note Modal ─────────────────────────────────────────────────────────

class OrderNoteModal(ui.Modal, title="📝 Detail Pembelian"):
    """
    Fallback modal untuk produk yang BELUM diset custom fields-nya.
    Hanya tampil voucher + catatan saja.
    """

    voucher = ui.TextInput(
        label="Kode Voucher (opsional)",
        placeholder="Masukkan kode voucher jika ada...",
        required=False,
        max_length=50,
    )
    notes = ui.TextInput(
        label="Catatan (opsional)",
        placeholder="Catatan tambahan untuk admin...",
        required=False,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, product, payment, db: "Database") -> None:
        super().__init__()
        self.product = product
        self.payment = payment
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from cogs.order import process_purchase

        await process_purchase(
            interaction=interaction,
            db=self.db,
            product=self.product,
            payment=self.payment,
            voucher_code=self.voucher.value.strip(),
            notes=self.notes.value.strip(),
            customer_info={},
        )


# ─── Dynamic Order Modal ──────────────────────────────────────────────────────

class DynamicOrderModal(ui.Modal):
    """
    Modal pembelian dengan field dinamis per produk.
    Field di-generate dari tabel product_fields (max 4 custom + 1 voucher = 5 total).
    Dipakai untuk produk TANPA varian maupun DENGAN varian.
    """

    def __init__(
        self,
        product,
        payment,
        db: "Database",
        fields: list,          # list of sqlite3.Row from product_fields
        variant=None,          # jika produk dengan varian
    ) -> None:
        super().__init__(title="📝 Detail Pembelian")
        self.product = product
        self.payment = payment
        self.db = db
        self.variant = variant
        self._field_keys: list[str] = []   # urutan key untuk baca nilai nanti

        # ── Tambah field custom (max 4 agar slot ke-5 untuk voucher) ──────────
        for i, f in enumerate(fields[:4]):
            key = f"custom_field_{i}"
            self._field_keys.append(key)
            text_input = ui.TextInput(
                label=f["label"][:45],
                placeholder=f["placeholder"][:100] if f["placeholder"] else "",
                required=bool(f["is_required"]),
                max_length=200,
            )
            self.add_item(text_input)

        # ── Slot terakhir selalu voucher ──────────────────────────────────────
        self._voucher_input = ui.TextInput(
            label="Kode Voucher (opsional)",
            placeholder="Masukkan kode voucher jika ada...",
            required=False,
            max_length=50,
        )
        self.add_item(self._voucher_input)

    def _collect_customer_info(self, fields: list) -> dict:
        """Kumpulkan nilai yang diisi user, map ke label field."""
        result: dict[str, str] = {}
        children = [
            item for item in self.children
            if isinstance(item, ui.TextInput) and item is not self._voucher_input
        ]
        for i, field_row in enumerate(fields[:4]):
            if i < len(children):
                val = children[i].value.strip()
                result[field_row["label"]] = val
        return result

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Ambil kembali fields dari DB untuk mapping label
        fields = await self.db.get_product_fields(self.product["id"])
        customer_info = self._collect_customer_info(fields)
        voucher_code = self._voucher_input.value.strip()

        if self.variant:
            from cogs.order import process_purchase_variant
            await process_purchase_variant(
                interaction=interaction,
                db=self.db,
                product=self.product,
                variant=self.variant,
                payment=self.payment,
                voucher_code=voucher_code,
                notes="",
                customer_info=customer_info,
            )
        else:
            from cogs.order import process_purchase
            await process_purchase(
                interaction=interaction,
                db=self.db,
                product=self.product,
                payment=self.payment,
                voucher_code=voucher_code,
                notes="",
                customer_info=customer_info,
            )


# ─── Ticket Action View (Persistent) ─────────────────────────────────────────

class TicketActionView(ui.View):
    """Persistent ticket control buttons shown inside a ticket channel."""

    def __init__(self, db: "Database") -> None:
        super().__init__(timeout=None)
        self.db = db

    @ui.button(
        label="✅ Konfirmasi",
        style=discord.ButtonStyle.success,
        custom_id="ticket:confirm",
    )
    async def confirm_order(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                "❌ Hanya admin yang bisa mengkonfirmasi.", ephemeral=True
            )
        from cogs.order import confirm_order_in_ticket

        await confirm_order_in_ticket(interaction, self.db)

    @ui.button(
        label="❌ Batalkan",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:cancel",
    )
    async def cancel_order(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                "❌ Hanya admin yang bisa membatalkan.", ephemeral=True
            )
        from cogs.order import cancel_order_in_ticket

        await cancel_order_in_ticket(interaction, self.db)

    @ui.button(
        label="🔒 Close Ticket",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        from cogs.ticket import close_ticket_channel

        await close_ticket_channel(interaction, self.db)

    @ui.button(
        label="🗑️ Delete Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:delete",
        row=1,
    )
    async def delete_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                "❌ Hanya admin yang bisa menghapus ticket.", ephemeral=True
            )
        from cogs.ticket import delete_ticket_channel

        await delete_ticket_channel(interaction, self.db)


# ─── Admin Product Edit Modal ─────────────────────────────────────────────────

class ProductEditModal(ui.Modal, title="✏️ Edit Produk"):
    name = ui.TextInput(label="Nama Produk", max_length=100)
    description = ui.TextInput(
        label="Deskripsi", style=discord.TextStyle.paragraph, required=False, max_length=1000
    )
    price = ui.TextInput(label="Harga (angka)", max_length=20)
    emoji = ui.TextInput(label="Emoji", required=False, max_length=10, placeholder="🛍️")
    thumbnail = ui.TextInput(
        label="Thumbnail URL", required=False, max_length=500, placeholder="https://..."
    )

    def __init__(self, product, db: "Database", on_submit_cb) -> None:
        super().__init__()
        self.product = product
        self.db = db
        self._on_submit_cb = on_submit_cb
        # Pre-fill
        self.name.default = product["name"]
        self.description.default = product["description"] or ""
        self.price.default = str(int(product["price"]) if product["price"] == int(product["price"]) else product["price"])
        self.emoji.default = product["emoji"] or "🛍️"
        self.thumbnail.default = product["thumbnail_url"] or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_cb(interaction, self)


# ─── Category Edit Modal ──────────────────────────────────────────────────────

class CategoryEditModal(ui.Modal, title="✏️ Edit Kategori"):
    name = ui.TextInput(label="Nama Kategori", max_length=50)
    description = ui.TextInput(
        label="Deskripsi", required=False, max_length=200, style=discord.TextStyle.paragraph
    )
    emoji = ui.TextInput(label="Emoji", required=False, max_length=10, placeholder="📦")

    def __init__(self, category, db: "Database", on_submit_cb) -> None:
        super().__init__()
        self.category = category
        self.db = db
        self._on_submit_cb = on_submit_cb
        self.name.default = category["name"]
        self.description.default = category["description"] or ""
        self.emoji.default = category["emoji"] or "📦"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_cb(interaction, self)


# ─── Stock Input Modal ────────────────────────────────────────────────────────

class StockInputModal(ui.Modal, title="📦 Tambah Stok"):
    contents = ui.TextInput(
        label="Isi Stok (satu per baris)",
        style=discord.TextStyle.paragraph,
        placeholder="akun1\nakun2\nakun3\n...",
        max_length=4000,
    )

    def __init__(self, product, db: "Database") -> None:
        super().__init__()
        self.product = product
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.embeds import success_embed, error_embed
        from utils.helpers import is_admin

        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        lines = [l.strip() for l in self.contents.value.split("\n") if l.strip()]
        if not lines:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Tidak ada stok yang dimasukkan."), ephemeral=True
            )

        count = await self.db.add_stocks(self.product["id"], lines)
        await interaction.response.send_message(
            embed=success_embed(
                "Stok Ditambahkan",
                f"Berhasil menambah **{count}** stok untuk **{self.product['name']}**.",
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Stock Added",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=self.product["name"],
            details=f"+{count} items",
        )


# ─── Voucher Create Modal ─────────────────────────────────────────────────────

class VoucherCreateModal(ui.Modal, title="🎟️ Buat Voucher"):
    code = ui.TextInput(label="Kode Voucher", max_length=50, placeholder="HEMAT20")
    description = ui.TextInput(label="Deskripsi", required=False, max_length=200)
    discount_type = ui.TextInput(label="Tipe (percent/flat)", max_length=10, placeholder="percent")
    discount_value = ui.TextInput(label="Nilai Diskon", max_length=10, placeholder="20")
    max_uses = ui.TextInput(label="Maks Pemakaian (0=unlimited)", max_length=10, placeholder="0")

    def __init__(self, db: "Database") -> None:
        super().__init__()
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from utils.embeds import success_embed, error_embed
        from utils.helpers import parse_price

        dtype = self.discount_type.value.strip().lower()
        if dtype not in ("percent", "flat"):
            return await interaction.response.send_message(
                embed=error_embed("Error", "Tipe diskon harus `percent` atau `flat`."),
                ephemeral=True,
            )
        val = parse_price(self.discount_value.value)
        if val is None or val <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Nilai diskon tidak valid."), ephemeral=True
            )
        try:
            max_uses = int(self.max_uses.value.strip())
        except ValueError:
            max_uses = 0

        code = self.code.value.strip().upper()
        existing = await self.db.get_voucher(code)
        if existing:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Kode voucher `{code}` sudah ada."), ephemeral=True
            )

        await self.db.create_voucher(
            code=code,
            description=self.description.value.strip(),
            discount_type=dtype,
            discount_value=val,
            max_uses=max_uses,
        )
        await interaction.response.send_message(
            embed=success_embed("Voucher Dibuat", f"Voucher `{code}` berhasil dibuat."),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Voucher Created",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=code,
            details=f"Type: {dtype}, Value: {val}, MaxUses: {max_uses}",
        )


# ─── Variant Select View ──────────────────────────────────────────────────────

class VariantSelectView(ui.View):
    """View untuk user memilih varian produk sebelum beli."""

    def __init__(self, product, variants: list, payments: list, db: "Database") -> None:
        super().__init__(timeout=180)
        self.product = product
        self.variants = variants
        self.payments = payments
        self.db = db

        options = [
            discord.SelectOption(
                label=v["name"][:100],
                value=str(v["id"]),
                description=format_price(v["price"]),
            )
            for v in variants[:25]
        ]
        select = ui.Select(
            placeholder="🎛️ Pilih Tipe/Varian...",
            options=options,
        )
        select.callback = self._variant_selected
        self.add_item(select)

    async def _variant_selected(self, interaction: discord.Interaction) -> None:
        from utils.embeds import error_embed, _base_embed
        from config import Config

        variant_id = int(interaction.data["values"][0])
        variant = await self.db.get_variant(variant_id)
        if not variant:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Varian tidak ditemukan."), ephemeral=True
            )

        stock_count = await self.db.get_stock_count_by_variant(self.product["id"], variant_id)
        payment_str = " • ".join(p["name"] for p in self.payments) if self.payments else "Tidak ada"

        embed = _base_embed(
            title=f"{self.product['emoji']} {self.product['name']}",
            description=f"**Tipe:** {variant['name']}\n\n{self.product['description'] or ''}",
            color=Config.COLOR_PRIMARY if stock_count > 0 else Config.COLOR_ERROR,
        )
        embed.add_field(name="💰 Harga", value=format_price(variant["price"]), inline=True)
        embed.add_field(name="📦 Stok", value=f"**{stock_count}** tersedia" if stock_count > 0 else "❌ Habis", inline=True)
        embed.add_field(name="💳 Payment", value=payment_str, inline=False)

        if self.product["thumbnail_url"]:
            embed.set_thumbnail(url=self.product["thumbnail_url"])

        view = VariantActionView(self.product, variant, stock_count, self.payments, self.db)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class VariantActionView(ui.View):
    """Buy / Refresh untuk produk dengan varian."""

    def __init__(self, product, variant, stock_count: int, payments: list, db: "Database") -> None:
        super().__init__(timeout=180)
        self.product = product
        self.variant = variant
        self.db = db
        self.payments = payments

        buy_btn = ui.Button(
            label="🛒 Beli Sekarang",
            style=discord.ButtonStyle.success,
            disabled=stock_count == 0,
        )
        buy_btn.callback = self._buy_now
        self.add_item(buy_btn)

        refresh_btn = ui.Button(
            label="🔄 Refresh Stok",
            style=discord.ButtonStyle.secondary,
        )
        refresh_btn.callback = self._refresh
        self.add_item(refresh_btn)

    async def _buy_now(self, interaction: discord.Interaction) -> None:
        from utils.embeds import error_embed
        if not self.payments:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Tidak ada metode pembayaran."), ephemeral=True
            )
        view = VariantPaymentSelectView(self.product, self.variant, self.payments, self.db)
        await interaction.response.send_message(
            content="💳 Pilih metode pembayaran:", view=view, ephemeral=True
        )

    async def _refresh(self, interaction: discord.Interaction) -> None:
        from utils.embeds import _base_embed
        from config import Config
        stock_count = await self.db.get_stock_count_by_variant(self.product["id"], self.variant["id"])
        view = VariantActionView(self.product, self.variant, stock_count, self.payments, self.db)
        embed = _base_embed(
            title=f"{self.product['emoji']} {self.product['name']}",
            description=f"**Tipe:** {self.variant['name']}",
            color=Config.COLOR_PRIMARY if stock_count > 0 else Config.COLOR_ERROR,
        )
        embed.add_field(name="💰 Harga", value=format_price(self.variant["price"]), inline=True)
        embed.add_field(name="📦 Stok", value=str(stock_count) if stock_count > 0 else "❌ Habis", inline=True)
        await interaction.response.edit_message(embed=embed, view=view)


class VariantPaymentSelectView(ui.View):
    def __init__(self, product, variant, payments: list, db: "Database") -> None:
        super().__init__(timeout=120)
        self.product = product
        self.variant = variant
        self.db = db

        options = [
            discord.SelectOption(label=p["name"], value=str(p["id"]))
            for p in payments[:25]
        ]
        select = ui.Select(placeholder="💳 Pilih Metode Pembayaran...", options=options)
        select.callback = self._payment_selected
        self.add_item(select)

    async def _payment_selected(self, interaction: discord.Interaction) -> None:
        from utils.embeds import error_embed
        payment_id = int(interaction.data["values"][0])
        payment = await self.db.get_payment(payment_id)
        if not payment:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Payment tidak ditemukan."), ephemeral=True
            )
        # Cek custom fields per produk
        fields = await self.db.get_product_fields(self.product["id"])
        if fields:
            modal = DynamicOrderModal(self.product, payment, self.db, fields, variant=self.variant)
        else:
            modal = VariantOrderModal(self.product, self.variant, payment, self.db)
        await interaction.response.send_modal(modal)


class VariantOrderModal(ui.Modal, title="📝 Detail Pembelian"):
    """
    Fallback modal untuk varian produk yang BELUM diset custom fields-nya.
    """

    voucher = ui.TextInput(label="Kode Voucher (opsional)", required=False, max_length=50)
    notes = ui.TextInput(
        label="Catatan (opsional)", required=False, max_length=300,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, product, variant, payment, db: "Database") -> None:
        super().__init__()
        self.product = product
        self.variant = variant
        self.payment = payment
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from cogs.order import process_purchase_variant
        await process_purchase_variant(
            interaction=interaction,
            db=self.db,
            product=self.product,
            variant=self.variant,
            payment=self.payment,
            voucher_code=self.voucher.value.strip(),
            notes=self.notes.value.strip(),
            customer_info={},
        )


# ─── Payment Proof View (Persistent) ─────────────────────────────────────────

class PaymentProofView(ui.View):
    """Tombol upload bukti pembayaran di ticket."""

    def __init__(self, order_id: int, db: "Database") -> None:
        super().__init__(timeout=None)
        self.order_id = order_id
        self.db = db

    @ui.button(
        label="📸 Upload Bukti Pembayaran",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:upload_proof",
    )
    async def upload_proof(self, interaction: discord.Interaction, button: ui.Button) -> None:
        from utils.embeds import error_embed
        ticket = await self.db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Ticket tidak ditemukan."), ephemeral=True
            )
        if interaction.user.id != ticket["user_id"]:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Hanya pemilik ticket yang bisa upload bukti."), ephemeral=True
            )
        modal = PaymentProofModal(self.order_id, self.db)
        await interaction.response.send_modal(modal)


class PaymentProofModal(ui.Modal, title="📸 Upload Bukti Pembayaran"):
    proof_url = ui.TextInput(
        label="Link Screenshot Bukti Transfer",
        placeholder="https://i.imgur.com/xxxxx.jpg",
        max_length=500,
    )
    note = ui.TextInput(
        label="Catatan Tambahan (opsional)",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, order_id: int, db: "Database") -> None:
        super().__init__()
        self.order_id = order_id
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        import re
        from utils.embeds import success_embed, error_embed
        from config import Config

        url = self.proof_url.value.strip()
        if not re.match(r"https?://", url):
            return await interaction.response.send_message(
                embed=error_embed("URL Tidak Valid", "Link harus dimulai dengan https://"),
                ephemeral=True,
            )

        await self.db.update_order(self.order_id, payment_proof_url=url, proof_submitted=1)

        embed = discord.Embed(
            title="📸 Bukti Pembayaran Diterima",
            description=f"{interaction.user.mention} telah mengirim bukti pembayaran.",
            color=Config.COLOR_INFO,
        )
        embed.set_image(url=url)
        if self.note.value:
            embed.add_field(name="📝 Catatan", value=self.note.value, inline=False)
        embed.set_footer(text="Admin silakan verifikasi dan klik Konfirmasi.")

        admin_role = interaction.guild.get_role(Config.ADMIN_ROLE_ID)
        ping = admin_role.mention if admin_role else "Admin"

        await interaction.channel.send(
            content=f"🔔 **Bukti pembayaran baru!** {ping}",
            embed=embed,
        )
        await interaction.response.send_message(
            embed=success_embed("Bukti Terkirim!", "Bukti pembayaran sudah dikirim ke admin. Tunggu konfirmasi ya!"),
            ephemeral=True,
        )
