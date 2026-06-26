"""
cogs/store.py — Main store dashboard cog.
Handles /setup-store and store main view initialization.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from database.database import Database
from utils.embeds import store_main_embed, success_embed, error_embed, info_embed
from utils.views import StoreMainView
from utils.helpers import is_admin, send_log

logger = logging.getLogger("store.cog.store")


class StoreCog(commands.Cog, name="Store"):
    """Main store dashboard commands."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    @app_commands.command(name="setup-store", description="Setup atau refresh tampilan store utama.")
    @app_commands.guild_only()
    async def setup_store(self, interaction: discord.Interaction) -> None:
        """Send the main store embed with category select to the store channel."""
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin yang bisa menjalankan perintah ini."),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        settings = await self.db.get_all_settings()
        categories = await self.db.get_categories(active_only=True)

        embed = store_main_embed(settings)
        view = StoreMainView(categories, self.db)

        target_channel_id = Config.STORE_CHANNEL_ID or interaction.channel_id
        channel = self.bot.get_channel(target_channel_id) or interaction.channel

        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(
                embed=error_embed("Error", "Channel store tidak valid."), ephemeral=True
            )

        try:
            await channel.send(embed=embed, view=view)
            await interaction.followup.send(
                embed=success_embed(
                    "Store Setup",
                    f"Store berhasil di-setup di {channel.mention}!",
                ),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Store Setup",
                actor_id=interaction.user.id,
                actor_name=str(interaction.user),
                details=f"Store embed sent to #{channel.name}",
                guild_id=interaction.guild_id or 0,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Error", "Bot tidak punya permission untuk mengirim pesan di channel tersebut."),
                ephemeral=True,
            )

    @app_commands.command(name="store-stats", description="Lihat statistik lengkap store.")
    @app_commands.guild_only()
    async def store_stats(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        stats = await self.db.get_full_stats()
        top_products = await self.db.get_top_selling_products(limit=5)
        top_customers = await self.db.get_top_customers(limit=3)

        from utils.embeds import stats_embed, format_price
        embed = stats_embed(stats, top_products)

        if top_customers:
            from utils.helpers import format_price as fp
            cust_text = "\n".join(
                f"{i+1}. <@{c['user_id']}> — {c['total_orders']} order"
                for i, c in enumerate(top_customers)
            )
            embed.add_field(name="👑 Top Pembeli", value=cust_text, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="store-config", description="Ubah konfigurasi store melalui Discord.")
    @app_commands.guild_only()
    @app_commands.describe(
        key="Nama setting (store_name, store_description, store_banner, store_thumbnail)",
        value="Nilai baru",
    )
    async def store_config(
        self,
        interaction: discord.Interaction,
        key: str,
        value: str,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        allowed_keys = {"store_name", "store_description", "store_banner", "store_thumbnail", "welcome_message"}
        if key not in allowed_keys:
            return await interaction.response.send_message(
                embed=error_embed(
                    "Key Tidak Valid",
                    f"Key yang diperbolehkan: `{'`, `'.join(allowed_keys)}`",
                ),
                ephemeral=True,
            )

        await self.db.set_setting(key, value)
        await interaction.response.send_message(
            embed=success_embed("Config Updated", f"`{key}` = `{value[:100]}`"),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Config Updated",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=key,
            details=value[:200],
        )

    @app_commands.command(name="my-orders", description="Lihat riwayat pembelian kamu.")
    @app_commands.guild_only()
    async def my_orders(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        from utils.embeds import purchase_history_embed
        from utils.helpers import chunk_list

        items_per_page = Config.ITEMS_PER_PAGE
        history = await self.db.get_user_purchase_history(
            interaction.user.id, limit=items_per_page * 10
        )

        if not history:
            return await interaction.followup.send(
                embed=info_embed("Riwayat Kosong", "Kamu belum pernah melakukan pembelian."),
                ephemeral=True,
            )

        pages = chunk_list(list(history), items_per_page)
        total_pages = len(pages)

        embed = purchase_history_embed(pages[0], interaction.user, page=1, total_pages=total_pages)

        if total_pages > 1:
            view = HistoryPaginationView(
                interaction.user.id, pages, interaction.user, self.db
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="search", description="Cari produk di store.")
    @app_commands.guild_only()
    @app_commands.describe(query="Kata kunci pencarian")
    async def search_products(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=True)

        products = await self.db.search_products(query)
        if not products:
            return await interaction.followup.send(
                embed=info_embed("Tidak Ditemukan", f"Tidak ada produk yang cocok dengan `{query}`."),
                ephemeral=True,
            )

        from utils.views import ProductSelectView
        view = ProductSelectView(products, self.db)
        await interaction.followup.send(
            content=f"🔍 Hasil pencarian untuk `{query}` ({len(products)} produk):",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="backup", description="Backup database secara manual.")
    @app_commands.guild_only()
    async def backup_db(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        import shutil
        import os
        from datetime import datetime

        backup_dir = "logs/backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        src = Config.DATABASE_PATH
        dst = f"{backup_dir}/store_{timestamp}.db"

        try:
            shutil.copy2(src, dst)
            size_kb = os.path.getsize(dst) // 1024
            await interaction.followup.send(
                embed=success_embed(
                    "Backup Berhasil",
                    f"Database berhasil di-backup.\n📁 File: `{dst}`\n💾 Ukuran: {size_kb} KB",
                ),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Database Backup",
                actor_id=interaction.user.id,
                actor_name=str(interaction.user),
                details=f"Backup: {dst} ({size_kb} KB)",
            )
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            await interaction.followup.send(
                embed=error_embed("Backup Gagal", str(e)), ephemeral=True
            )


class HistoryPaginationView(discord.ui.View):
    def __init__(self, author_id: int, pages: list, user: discord.Member, db: Database) -> None:
        super().__init__(timeout=120)
        self.author_id = author_id
        self.pages = pages
        self.user = user
        self.db = db
        self.current = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current <= 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current -= 1
        self._update_buttons()
        from utils.embeds import purchase_history_embed
        embed = purchase_history_embed(self.pages[self.current], self.user, self.current + 1, len(self.pages))
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current += 1
        self._update_buttons()
        from utils.embeds import purchase_history_embed
        embed = purchase_history_embed(self.pages[self.current], self.user, self.current + 1, len(self.pages))
        await interaction.response.edit_message(embed=embed, view=self)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StoreCog(bot, bot.db))
