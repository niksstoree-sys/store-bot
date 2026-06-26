"""
cogs/product.py — Product management commands.
Admin-only: /product add | edit | delete | list | info
"""

import logging
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.database import Database
from utils.embeds import (
    success_embed, error_embed, info_embed, product_embed,
    product_list_embed, _base_embed,
)
from utils.helpers import is_admin, clean_input, parse_price, format_price, chunk_list
from utils.views import ProductEditModal
from config import Config

logger = logging.getLogger("store.cog.product")


class ProductCog(commands.Cog, name="Product"):
    """Product management commands."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    product_group = app_commands.Group(
        name="product", description="Kelola produk di store."
    )

    # ─── /product add ─────────────────────────────────────────────────────────

    @product_group.command(name="add", description="Tambah produk baru.")
    @app_commands.guild_only()
    @app_commands.describe(
        category_id="ID kategori produk",
        name="Nama produk",
        price="Harga produk (angka)",
        description="Deskripsi produk",
        emoji="Emoji produk",
        thumbnail_url="URL thumbnail produk",
        banner_url="URL banner produk",
        role_id="ID role yang akan diberikan setelah pembelian",
    )
    async def product_add(
        self,
        interaction: discord.Interaction,
        category_id: int,
        name: str,
        price: str,
        description: str = "",
        emoji: str = "🛍️",
        thumbnail_url: str = "",
        banner_url: str = "",
        role_id: Optional[str] = None,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        category = await self.db.get_category(category_id)
        if not category:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Kategori ID `{category_id}` tidak ditemukan."),
                ephemeral=True,
            )

        parsed_price = parse_price(price)
        if parsed_price is None or parsed_price < 0:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Harga tidak valid. Masukkan angka."), ephemeral=True
            )

        parsed_role_id = 0
        if role_id:
            try:
                parsed_role_id = int(role_id)
            except ValueError:
                pass

        product_id = await self.db.create_product(
            category_id=category_id,
            name=clean_input(name),
            description=clean_input(description),
            price=parsed_price,
            emoji=emoji.strip() or "🛍️",
            thumbnail_url=thumbnail_url.strip(),
            banner_url=banner_url.strip(),
            role_id=parsed_role_id,
        )

        # Automatically assign all active payments to this product
        all_payments = await self.db.get_payments(active_only=True)
        if all_payments:
            payment_ids = [p["id"] for p in all_payments]
            await self.db.set_product_payments(product_id, payment_ids)

        await interaction.response.send_message(
            embed=success_embed(
                "Produk Ditambahkan",
                f"{emoji} **{name}** berhasil ditambahkan ke **{category['name']}**!\n"
                f"ID: `{product_id}` | Harga: {format_price(parsed_price)}",
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Product Added",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=name,
            details=f"ID: {product_id}, Price: {format_price(parsed_price)}, Category: {category['name']}",
            guild_id=interaction.guild_id or 0,
        )

    # ─── /product edit ────────────────────────────────────────────────────────

    @product_group.command(name="edit", description="Edit produk yang ada.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk yang ingin diedit")
    async def product_edit(
        self, interaction: discord.Interaction, product_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        async def on_submit(interaction: discord.Interaction, modal: ProductEditModal) -> None:
            parsed_price = parse_price(modal.price.value)
            if parsed_price is None or parsed_price < 0:
                return await interaction.response.send_message(
                    embed=error_embed("Error", "Harga tidak valid."), ephemeral=True
                )
            new_name = clean_input(modal.name.value)
            if not new_name:
                return await interaction.response.send_message(
                    embed=error_embed("Error", "Nama tidak boleh kosong."), ephemeral=True
                )

            await self.db.update_product(
                product_id,
                name=new_name,
                description=clean_input(modal.description.value),
                price=parsed_price,
                emoji=modal.emoji.value.strip() or "🛍️",
                thumbnail_url=modal.thumbnail.value.strip(),
            )
            await interaction.response.send_message(
                embed=success_embed(
                    "Produk Diupdate",
                    f"**{new_name}** berhasil diupdate. Harga: {format_price(parsed_price)}",
                ),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Product Edited",
                actor_id=interaction.user.id,
                actor_name=str(interaction.user),
                target=new_name,
                details=f"ID: {product_id}",
            )

        modal = ProductEditModal(product, self.db, on_submit)
        await interaction.response.send_modal(modal)

    # ─── /product delete ──────────────────────────────────────────────────────

    @product_group.command(name="delete", description="Hapus produk beserta semua stoknya.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk yang ingin dihapus")
    async def product_delete(
        self, interaction: discord.Interaction, product_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        from utils.views import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Konfirmasi Hapus",
                description=f"Kamu akan menghapus produk **{product['name']}** dan semua stoknya. Lanjutkan?",
                color=Config.COLOR_WARNING,
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            return await interaction.edit_original_response(
                embed=info_embed("Dibatalkan", "Penghapusan dibatalkan."), view=None
            )

        prod_name = product["name"]
        await self.db.delete_product(product_id)
        await interaction.edit_original_response(
            embed=success_embed("Produk Dihapus", f"Produk **{prod_name}** berhasil dihapus."),
            view=None,
        )
        await self.db.log_activity(
            action="Product Deleted",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=prod_name,
            details=f"ID: {product_id}",
        )

    # ─── /product list ────────────────────────────────────────────────────────

    @product_group.command(name="list", description="Tampilkan daftar produk.")
    @app_commands.guild_only()
    @app_commands.describe(category_id="Filter berdasarkan ID kategori (opsional)")
    async def product_list(
        self,
        interaction: discord.Interaction,
        category_id: Optional[int] = None,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        products = await self.db.get_products(category_id=category_id)

        if not products:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Belum ada produk."), ephemeral=True
            )

        embed = _base_embed(title="🛍️ Daftar Produk", color=Config.COLOR_PRIMARY)
        pages = chunk_list(list(products), Config.ITEMS_PER_PAGE)

        stock_counts: dict[int, int] = {}
        for p in products[:25]:  # Limit initial stock fetch
            stock_counts[p["id"]] = await self.db.get_product_stock_count(p["id"])

        for p in pages[0]:
            stock = stock_counts.get(p["id"], 0)
            embed.add_field(
                name=f"`ID:{p['id']}` {p['emoji']} {p['name']}",
                value=(
                    f"💰 {format_price(p['price'])} | 📦 Stok: {stock} | "
                    f"📂 {p['category_name']} | {'✅' if p['status'] == 'active' else '❌'}"
                ),
                inline=False,
            )

        if len(pages) > 1:
            embed.set_footer(text=f"⚡ {Config.STORE_NAME} | Halaman 1/{len(pages)} | Total: {len(products)}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /product info ────────────────────────────────────────────────────────

    @product_group.command(name="info", description="Lihat detail produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def product_info(
        self, interaction: discord.Interaction, product_id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.followup.send(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        stock_count = await self.db.get_product_stock_count(product_id)
        payments = await self.db.get_product_payments(product_id)

        embed = product_embed(product, stock_count, payments)

        if is_admin(interaction.user):
            # Show extra admin info
            all_stocks = await self.db.get_stocks(product_id, sold=False)
            sold_stocks = await self.db.get_stocks(product_id, sold=True)
            embed.add_field(name="📊 Stok Terjual", value=str(len(sold_stocks)), inline=True)
            embed.add_field(name="📋 Status", value=product["status"], inline=True)
            embed.add_field(name="📂 Kategori", value=f"ID: {product['category_id']} — {product['category_name']}", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /product toggle ──────────────────────────────────────────────────────

    @product_group.command(name="toggle", description="Aktif/nonaktifkan produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def product_toggle(
        self, interaction: discord.Interaction, product_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        new_status = "inactive" if product["status"] == "active" else "active"
        await self.db.update_product(product_id, status=new_status)
        await interaction.response.send_message(
            embed=success_embed(
                "Produk Diupdate",
                f"Produk **{product['name']}** sekarang {'aktif ✅' if new_status == 'active' else 'nonaktif ❌'}.",
            ),
            ephemeral=True,
        )

    # ─── /product set-payments ────────────────────────────────────────────────

    @product_group.command(name="set-payments", description="Atur metode pembayaran untuk produk.")
    @app_commands.guild_only()
    @app_commands.describe(
        product_id="ID produk",
        payment_ids="ID payment dipisah koma (contoh: 1,2,3)",
    )
    async def product_set_payments(
        self,
        interaction: discord.Interaction,
        product_id: int,
        payment_ids: str,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        try:
            ids = [int(x.strip()) for x in payment_ids.split(",") if x.strip()]
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Format ID payment tidak valid."), ephemeral=True
            )

        await self.db.set_product_payments(product_id, ids)
        await interaction.response.send_message(
            embed=success_embed(
                "Payment Diupdate",
                f"Payment untuk **{product['name']}** berhasil diset ke ID: `{', '.join(map(str, ids))}`",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProductCog(bot, bot.db))
