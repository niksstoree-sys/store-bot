"""
cogs/category.py — Category management commands.
Admin-only: /category add | edit | delete | list
"""

import logging

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, _base_embed
from utils.helpers import is_admin, clean_input
from utils.views import CategoryEditModal
from config import Config

logger = logging.getLogger("store.cog.category")


class CategoryCog(commands.Cog, name="Category"):
    """Category management commands."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    category_group = app_commands.Group(
        name="category", description="Kelola kategori produk store."
    )

    # ─── /category add ────────────────────────────────────────────────────────

    @category_group.command(name="add", description="Tambah kategori baru.")
    @app_commands.guild_only()
    @app_commands.describe(
        name="Nama kategori",
        description="Deskripsi singkat kategori",
        emoji="Emoji untuk kategori (default: 📦)",
        position="Urutan tampil (semakin kecil semakin atas)",
    )
    async def category_add(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = "",
        emoji: str = "📦",
        position: int = 0,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        name = clean_input(name)
        if not name:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Nama kategori tidak boleh kosong."), ephemeral=True
            )

        existing = await self.db.get_category_by_name(name)
        if existing:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Kategori `{name}` sudah ada."), ephemeral=True
            )

        cat_id = await self.db.create_category(
            name=name,
            description=clean_input(description),
            emoji=emoji.strip() or "📦",
            position=position,
        )
        await interaction.response.send_message(
            embed=success_embed(
                "Kategori Ditambahkan",
                f"{emoji} **{name}** berhasil ditambahkan! (ID: {cat_id})",
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Category Added",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=name,
            details=f"ID: {cat_id}, Emoji: {emoji}",
            guild_id=interaction.guild_id or 0,
        )
        logger.info(f"Category added: {name} (ID={cat_id}) by {interaction.user}")

    # ─── /category edit ───────────────────────────────────────────────────────

    @category_group.command(name="edit", description="Edit kategori yang ada.")
    @app_commands.guild_only()
    @app_commands.describe(category_id="ID kategori yang ingin diedit")
    async def category_edit(
        self, interaction: discord.Interaction, category_id: int
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

        async def on_submit(interaction: discord.Interaction, modal: CategoryEditModal) -> None:
            new_name = clean_input(modal.name.value)
            if not new_name:
                return await interaction.response.send_message(
                    embed=error_embed("Error", "Nama tidak boleh kosong."), ephemeral=True
                )
            await self.db.update_category(
                category_id,
                name=new_name,
                description=clean_input(modal.description.value),
                emoji=modal.emoji.value.strip() or "📦",
            )
            await interaction.response.send_message(
                embed=success_embed("Kategori Diupdate", f"**{new_name}** berhasil diupdate."),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Category Edited",
                actor_id=interaction.user.id,
                actor_name=str(interaction.user),
                target=new_name,
                details=f"ID: {category_id}",
            )

        modal = CategoryEditModal(category, self.db, on_submit)
        await interaction.response.send_modal(modal)

    # ─── /category delete ─────────────────────────────────────────────────────

    @category_group.command(name="delete", description="Hapus kategori beserta semua produknya.")
    @app_commands.guild_only()
    @app_commands.describe(category_id="ID kategori yang ingin dihapus")
    async def category_delete(
        self, interaction: discord.Interaction, category_id: int
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

        products = await self.db.get_products(category_id=category_id)
        product_count = len(products)

        from utils.views import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Konfirmasi Hapus",
                description=(
                    f"Kamu akan menghapus kategori **{category['name']}**.\n"
                    f"Ini juga akan menghapus **{product_count} produk** dan semua stoknya!\n\n"
                    "Lanjutkan?"
                ),
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

        cat_name = category["name"]
        await self.db.delete_category(category_id)
        await interaction.edit_original_response(
            embed=success_embed("Kategori Dihapus", f"Kategori **{cat_name}** berhasil dihapus."),
            view=None,
        )
        await self.db.log_activity(
            action="Category Deleted",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=cat_name,
            details=f"ID: {category_id}, Products deleted: {product_count}",
        )

    # ─── /category list ───────────────────────────────────────────────────────

    @category_group.command(name="list", description="Tampilkan semua kategori.")
    @app_commands.guild_only()
    async def category_list(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        categories = await self.db.get_categories()

        if not categories:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Belum ada kategori."), ephemeral=True
            )

        embed = _base_embed(title="📂 Daftar Kategori", color=Config.COLOR_PRIMARY)
        for cat in categories:
            status = "✅ Aktif" if cat["is_active"] else "❌ Nonaktif"
            products = await self.db.get_products(category_id=cat["id"])
            embed.add_field(
                name=f"`ID:{cat['id']}` {cat['emoji']} {cat['name']}",
                value=(
                    f"📝 {cat['description'] or 'Tidak ada deskripsi'}\n"
                    f"📦 {len(products)} produk | Pos: {cat['position']} | {status}"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /category toggle ─────────────────────────────────────────────────────

    @category_group.command(name="toggle", description="Aktif/nonaktifkan kategori.")
    @app_commands.guild_only()
    @app_commands.describe(category_id="ID kategori")
    async def category_toggle(
        self, interaction: discord.Interaction, category_id: int
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

        new_status = 0 if category["is_active"] else 1
        await self.db.update_category(category_id, is_active=new_status)
        status_text = "diaktifkan" if new_status else "dinonaktifkan"
        await interaction.response.send_message(
            embed=success_embed(
                "Kategori Diupdate",
                f"Kategori **{category['name']}** berhasil {status_text}.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CategoryCog(bot, bot.db))
