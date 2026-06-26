"""
cogs/variant.py — Product variant management.
Admin: /variant add | edit | delete | list
User: Variant select menu saat membeli produk.
"""

import logging
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, _base_embed
from utils.helpers import is_admin, format_price, parse_price, clean_input
from config import Config

logger = logging.getLogger("store.cog.variant")


class VariantAddModal(ui.Modal, title="➕ Tambah Varian Produk"):
    name = ui.TextInput(label="Nama Varian", max_length=100, placeholder="400 Robux / Vilog 5 Hari / Gift Card $5")
    price = ui.TextInput(label="Harga", max_length=20, placeholder="15900")
    position = ui.TextInput(label="Urutan (opsional)", required=False, max_length=5, placeholder="1")


class VariantEditModal(ui.Modal, title="✏️ Edit Varian"):
    name = ui.TextInput(label="Nama Varian", max_length=100)
    price = ui.TextInput(label="Harga", max_length=20)

    def __init__(self, variant, db: Database, on_submit_cb) -> None:
        super().__init__()
        self.variant = variant
        self.db = db
        self._cb = on_submit_cb
        self.name.default = variant["name"]
        self.price.default = str(int(variant["price"]) if variant["price"] == int(variant["price"]) else variant["price"])

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._cb(interaction, self)


class VariantCog(commands.Cog, name="Variant"):
    """Product variant management."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    variant_group = app_commands.Group(
        name="variant", description="Kelola varian/tipe produk."
    )

    @variant_group.command(name="add", description="Tambah varian ke produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def variant_add(self, interaction: discord.Interaction, product_id: int) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."), ephemeral=True
            )

        modal = VariantAddModal()

        async def on_submit(inter: discord.Interaction) -> None:
            name = clean_input(modal.name.value)
            price = parse_price(modal.price.value)
            if not name:
                return await inter.response.send_message(
                    embed=error_embed("Error", "Nama varian tidak boleh kosong."), ephemeral=True
                )
            if price is None or price < 0:
                return await inter.response.send_message(
                    embed=error_embed("Error", "Harga tidak valid."), ephemeral=True
                )
            try:
                pos = int(modal.position.value.strip()) if modal.position.value.strip() else 0
            except ValueError:
                pos = 0

            vid = await self.db.create_variant(product_id, name, price, pos)
            await inter.response.send_message(
                embed=success_embed(
                    "Varian Ditambahkan",
                    f"Varian **{name}** ({format_price(price)}) ditambahkan ke **{product['name']}**! (ID: {vid})",
                ),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Variant Added",
                actor_id=inter.user.id,
                actor_name=str(inter.user),
                target=f"{product['name']} → {name}",
                details=f"Price: {format_price(price)}",
            )

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @variant_group.command(name="list", description="Tampilkan semua varian produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def variant_list(self, interaction: discord.Interaction, product_id: int) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.followup.send(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."), ephemeral=True
            )

        variants = await self.db.get_all_product_variants(product_id)
        if not variants:
            return await interaction.followup.send(
                embed=info_embed("Kosong", f"Produk **{product['name']}** belum punya varian."), ephemeral=True
            )

        embed = _base_embed(
            title=f"🎛️ Varian — {product['name']}",
            color=Config.COLOR_PRIMARY,
        )
        for v in variants:
            stock = await self.db.get_stock_count_by_variant(product_id, v["id"])
            status = "✅" if v["is_active"] else "❌"
            embed.add_field(
                name=f"`ID:{v['id']}` {status} {v['name']}",
                value=f"💰 {format_price(v['price'])} | 📦 Stok: {stock} | Pos: {v['position']}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @variant_group.command(name="edit", description="Edit varian produk.")
    @app_commands.guild_only()
    @app_commands.describe(variant_id="ID varian")
    async def variant_edit(self, interaction: discord.Interaction, variant_id: int) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        variant = await self.db.get_variant(variant_id)
        if not variant:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Varian ID `{variant_id}` tidak ditemukan."), ephemeral=True
            )

        async def on_submit(inter: discord.Interaction, modal: VariantEditModal) -> None:
            name = clean_input(modal.name.value)
            price = parse_price(modal.price.value)
            if not name or price is None:
                return await inter.response.send_message(
                    embed=error_embed("Error", "Input tidak valid."), ephemeral=True
                )
            await self.db.update_variant(variant_id, name=name, price=price)
            await inter.response.send_message(
                embed=success_embed("Varian Diupdate", f"**{name}** ({format_price(price)}) berhasil diupdate."),
                ephemeral=True,
            )

        modal = VariantEditModal(variant, self.db, on_submit)
        await interaction.response.send_modal(modal)

    @variant_group.command(name="delete", description="Hapus varian produk.")
    @app_commands.guild_only()
    @app_commands.describe(variant_id="ID varian")
    async def variant_delete(self, interaction: discord.Interaction, variant_id: int) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        variant = await self.db.get_variant(variant_id)
        if not variant:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Varian ID `{variant_id}` tidak ditemukan."), ephemeral=True
            )

        from utils.views import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Hapus Varian",
                description=f"Hapus varian **{variant['name']}**? Stok varian ini juga akan terhapus.",
                color=Config.COLOR_WARNING,
            ),
            view=view, ephemeral=True,
        )
        await view.wait()
        if not view.confirmed:
            return await interaction.edit_original_response(
                embed=info_embed("Dibatalkan", "Penghapusan dibatalkan."), view=None
            )
        await self.db.delete_variant(variant_id)
        await interaction.edit_original_response(
            embed=success_embed("Varian Dihapus", f"Varian **{variant['name']}** berhasil dihapus."),
            view=None,
        )

    @variant_group.command(name="stock-add", description="Tambah stok untuk varian tertentu.")
    @app_commands.guild_only()
    @app_commands.describe(variant_id="ID varian")
    async def variant_stock_add(self, interaction: discord.Interaction, variant_id: int) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        variant = await self.db.get_variant(variant_id)
        if not variant:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Varian ID `{variant_id}` tidak ditemukan."), ephemeral=True
            )

        modal = VariantStockModal(variant, self.db)
        await interaction.response.send_modal(modal)


class VariantStockModal(ui.Modal, title="📦 Tambah Stok Varian"):
    contents = ui.TextInput(
        label="Isi Stok (satu per baris)",
        style=discord.TextStyle.paragraph,
        placeholder="akun1:pass1\nakun2:pass2\n...",
        max_length=4000,
    )

    def __init__(self, variant, db: Database) -> None:
        super().__init__()
        self.variant = variant
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lines = [l.strip() for l in self.contents.value.split("\n") if l.strip()]
        if not lines:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Tidak ada stok yang dimasukkan."), ephemeral=True
            )
        count = await self.db.add_stocks(self.variant["product_id"], lines, variant_id=self.variant["id"])
        await interaction.response.send_message(
            embed=success_embed(
                "Stok Ditambahkan",
                f"✅ **{count}** stok ditambahkan untuk varian **{self.variant['name']}**.",
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Variant Stock Added",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=self.variant["name"],
            details=f"+{count} items",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VariantCog(bot, bot.db))
