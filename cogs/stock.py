"""
cogs/stock.py — Stock management commands.
Admin-only: /stock add | remove | view | clear
FIFO stock system with low-stock notifications.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, warning_embed, _base_embed
from utils.helpers import is_admin, chunk_list
from utils.views import StockInputModal
from config import Config

logger = logging.getLogger("store.cog.stock")


class StockCog(commands.Cog, name="Stock"):
    """Stock management commands."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self.low_stock_check.start()

    def cog_unload(self) -> None:
        self.low_stock_check.cancel()

    stock_group = app_commands.Group(
        name="stock", description="Kelola stok produk."
    )

    # ─── /stock add ───────────────────────────────────────────────────────────

    @stock_group.command(name="add", description="Tambah stok produk melalui modal (satu per baris).")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def stock_add(
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

        modal = StockInputModal(product, self.db)
        await interaction.response.send_modal(modal)

    # ─── /stock add-file ──────────────────────────────────────────────────────

    @stock_group.command(name="add-text", description="Tambah stok langsung via teks (pisah koma atau baris baru).")
    @app_commands.guild_only()
    @app_commands.describe(
        product_id="ID produk",
        content="Isi stok (pisahkan dengan koma atau baris baru)",
    )
    async def stock_add_text(
        self,
        interaction: discord.Interaction,
        product_id: int,
        content: str,
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

        lines: list[str] = []
        for part in content.replace(",", "\n").split("\n"):
            stripped = part.strip()
            if stripped:
                lines.append(stripped)

        if not lines:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Tidak ada stok yang dimasukkan."), ephemeral=True
            )

        count = await self.db.add_stocks(product_id, lines)
        await interaction.response.send_message(
            embed=success_embed(
                "Stok Ditambahkan",
                f"✅ Berhasil menambah **{count}** stok untuk **{product['name']}**.",
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Stock Added",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=product["name"],
            details=f"+{count} items",
            guild_id=interaction.guild_id or 0,
        )

    # ─── /stock remove ────────────────────────────────────────────────────────

    @stock_group.command(name="remove", description="Hapus item stok spesifik berdasarkan ID.")
    @app_commands.guild_only()
    @app_commands.describe(stock_id="ID stok yang ingin dihapus")
    async def stock_remove(
        self, interaction: discord.Interaction, stock_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        result = await self.db.remove_stock(stock_id)
        if result == 0:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Stok ID `{stock_id}` tidak ditemukan."),
                ephemeral=True,
            )

        await interaction.response.send_message(
            embed=success_embed("Stok Dihapus", f"Stok ID `{stock_id}` berhasil dihapus."),
            ephemeral=True,
        )

    # ─── /stock view ──────────────────────────────────────────────────────────

    @stock_group.command(name="view", description="Lihat stok produk.")
    @app_commands.guild_only()
    @app_commands.describe(
        product_id="ID produk",
        show_content="Tampilkan konten stok (default: False untuk keamanan)",
    )
    async def stock_view(
        self,
        interaction: discord.Interaction,
        product_id: int,
        show_content: bool = False,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.followup.send(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        stocks = await self.db.get_stocks(product_id, sold=False)
        sold_stocks = await self.db.get_stocks(product_id, sold=True)

        embed = _base_embed(
            title=f"📦 Stok — {product['name']}",
            color=Config.COLOR_INFO,
        )
        embed.add_field(name="✅ Tersedia", value=str(len(stocks)), inline=True)
        embed.add_field(name="✔️ Terjual", value=str(len(sold_stocks)), inline=True)
        embed.add_field(name="📊 Total", value=str(len(stocks) + len(sold_stocks)), inline=True)

        if show_content and stocks:
            pages = chunk_list(list(stocks), 10)
            content_lines = [
                f"`[{s['id']}]` {s['content'][:50]}{'...' if len(s['content']) > 50 else ''}"
                for s in pages[0]
            ]
            embed.add_field(
                name=f"📋 Preview Stok (10/{len(stocks)})",
                value="\n".join(content_lines) or "Kosong",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /stock clear ─────────────────────────────────────────────────────────

    @stock_group.command(name="clear", description="Hapus SEMUA stok yang belum terjual dari produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def stock_clear(
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

        stocks = await self.db.get_stocks(product_id, sold=False)
        if not stocks:
            return await interaction.response.send_message(
                embed=info_embed("Kosong", "Tidak ada stok tersedia untuk dihapus."),
                ephemeral=True,
            )

        from utils.views import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Konfirmasi Clear Stok",
                description=f"Kamu akan menghapus **{len(stocks)}** stok dari **{product['name']}**. Lanjutkan?",
                color=Config.COLOR_WARNING,
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            return await interaction.edit_original_response(
                embed=info_embed("Dibatalkan", "Clear stok dibatalkan."), view=None
            )

        for stock in stocks:
            await self.db.remove_stock(stock["id"])

        await interaction.edit_original_response(
            embed=success_embed(
                "Stok Dibersihkan",
                f"Berhasil menghapus {len(stocks)} stok dari **{product['name']}**.",
            ),
            view=None,
        )
        await self.db.log_activity(
            action="Stock Cleared",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=product["name"],
            details=f"Cleared {len(stocks)} items",
        )

    # ─── Background Task: Low Stock Check ────────────────────────────────────

    @tasks.loop(minutes=30)
    async def low_stock_check(self) -> None:
        """Check all products for low stock and notify log channel."""
        try:
            products = await self.db.get_products(active_only=True)
            threshold = Config.LOW_STOCK_THRESHOLD

            for product in products:
                stock_count = await self.db.get_product_stock_count(product["id"])
                if 0 < stock_count <= threshold:
                    await self._notify_low_stock(product, stock_count)
                elif stock_count == 0:
                    await self._notify_out_of_stock(product)
        except Exception as e:
            logger.error(f"Low stock check error: {e}")

    async def _notify_low_stock(self, product, stock_count: int) -> None:
        if not Config.LOG_CHANNEL_ID:
            return
        channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        if not channel:
            return
        embed = warning_embed(
            "⚠️ Stok Menipis",
            f"Produk **{product['name']}** hanya tersisa **{stock_count}** stok!\n"
            f"Segera tambah stok dengan `/stock add {product['id']}`",
        )
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    async def _notify_out_of_stock(self, product) -> None:
        """Notify only once per out-of-stock event using a cache."""
        cache_key = f"oos_{product['id']}"
        if hasattr(self, "_oos_notified") and cache_key in self._oos_notified:
            return
        if not hasattr(self, "_oos_notified"):
            self._oos_notified: set[str] = set()

        self._oos_notified.add(cache_key)

        if not Config.LOG_CHANNEL_ID:
            return
        channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
        if not channel:
            return
        embed = error_embed(
            "❌ Stok Habis!",
            f"Produk **{product['name']}** telah kehabisan stok!\n"
            f"Tambah stok segera: `/stock add {product['id']}`",
        )
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @low_stock_check.before_loop
    async def before_low_stock_check(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StockCog(bot, bot.db))
