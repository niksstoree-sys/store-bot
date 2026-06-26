"""
cogs/admin.py — Admin-only panel.
Voucher CRUD, activity logs, sales statistics, system management.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.database import Database
from utils.embeds import (
    success_embed, error_embed, info_embed, voucher_list_embed,
    _base_embed, warning_embed,
)
from utils.helpers import is_admin, is_owner, format_price, chunk_list
from utils.views import VoucherCreateModal
from config import Config

logger = logging.getLogger("store.cog.admin")


class AdminCog(commands.Cog, name="Admin"):
    """Admin panel and system management."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self.auto_backup.start()

    def cog_unload(self) -> None:
        self.auto_backup.cancel()

    # ─── Voucher Group ────────────────────────────────────────────────────────

    voucher_group = app_commands.Group(
        name="voucher", description="Kelola voucher dan diskon."
    )

    @voucher_group.command(name="create", description="Buat voucher baru.")
    @app_commands.guild_only()
    async def voucher_create(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        modal = VoucherCreateModal(self.db)
        await interaction.response.send_modal(modal)

    @voucher_group.command(name="list", description="Tampilkan semua voucher.")
    @app_commands.guild_only()
    async def voucher_list(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        vouchers = await self.db.get_all_vouchers()
        embed = voucher_list_embed(vouchers)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @voucher_group.command(name="delete", description="Hapus voucher.")
    @app_commands.guild_only()
    @app_commands.describe(code="Kode voucher yang ingin dihapus")
    async def voucher_delete(self, interaction: discord.Interaction, code: str) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        voucher = await self.db.get_voucher(code.upper())
        if not voucher:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Voucher `{code.upper()}` tidak ditemukan."),
                ephemeral=True,
            )
        await self.db.delete_voucher(voucher["id"])
        await interaction.response.send_message(
            embed=success_embed("Voucher Dihapus", f"Voucher `{code.upper()}` berhasil dihapus."),
            ephemeral=True,
        )

    @voucher_group.command(name="toggle", description="Aktif/nonaktifkan voucher.")
    @app_commands.guild_only()
    @app_commands.describe(code="Kode voucher")
    async def voucher_toggle(self, interaction: discord.Interaction, code: str) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        voucher = await self.db.get_voucher(code.upper())
        if not voucher:
            # Try find inactive voucher
            row = await self.db._execute(
                "SELECT * FROM vouchers WHERE UPPER(code) = UPPER(?)", (code,), fetch="one"
            )
            if not row:
                return await interaction.response.send_message(
                    embed=error_embed("Error", f"Voucher `{code.upper()}` tidak ditemukan."),
                    ephemeral=True,
                )
            voucher = row

        new_status = 0 if voucher["is_active"] else 1
        await self.db.update_voucher(voucher["id"], is_active=new_status)
        status_text = "diaktifkan ✅" if new_status else "dinonaktifkan ❌"
        await interaction.response.send_message(
            embed=success_embed("Voucher Diupdate", f"Voucher `{voucher['code']}` berhasil {status_text}."),
            ephemeral=True,
        )

    @voucher_group.command(name="check", description="Cek info voucher.")
    @app_commands.guild_only()
    @app_commands.describe(code="Kode voucher")
    async def voucher_check(self, interaction: discord.Interaction, code: str) -> None:
        row = await self.db._execute(
            "SELECT * FROM vouchers WHERE UPPER(code) = UPPER(?)", (code,), fetch="one"
        )
        if not row:
            return await interaction.response.send_message(
                embed=error_embed("Tidak Ditemukan", f"Voucher `{code.upper()}` tidak ada."),
                ephemeral=True,
            )
        disc = (
            f"{int(row['discount_value'])}%"
            if row["discount_type"] == "percent"
            else format_price(row["discount_value"])
        )
        uses = f"{row['used_count']}/{row['max_uses']}" if row["max_uses"] > 0 else f"{row['used_count']}/∞"
        status_text = "✅ Aktif" if row["is_active"] else "❌ Nonaktif"
        embed = _base_embed(title=f"🎟️ Voucher `{row['code']}`", color=Config.COLOR_GOLD)
        embed.add_field(name="Tipe", value=row["discount_type"].capitalize(), inline=True)
        embed.add_field(name="Diskon", value=disc, inline=True)
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="Pemakaian", value=uses, inline=True)
        embed.add_field(name="Min Beli", value=format_price(row["min_purchase"]), inline=True)
        embed.add_field(name="Expired", value=row["expires_at"] or "Tidak ada", inline=True)
        if row["description"]:
            embed.add_field(name="Deskripsi", value=row["description"], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─── Log Commands ─────────────────────────────────────────────────────────

    @app_commands.command(name="logs", description="[Admin] Lihat log aktivitas terbaru.")
    @app_commands.guild_only()
    @app_commands.describe(limit="Jumlah log yang ditampilkan (default: 15)")
    async def activity_logs(
        self, interaction: discord.Interaction, limit: int = 15
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        limit = max(1, min(limit, 50))
        logs = await self.db.get_recent_logs(limit)

        if not logs:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Belum ada aktivitas."), ephemeral=True
            )

        embed = _base_embed(title=f"📋 Log Aktivitas (Terakhir {limit})", color=Config.COLOR_INFO)
        for log in logs:
            embed.add_field(
                name=f"`{log['created_at'][:16]}` — {log['action']}",
                value=(
                    f"👤 {log['actor_name'] or 'System'}\n"
                    f"🎯 {log['target'] or '-'}: {log['details'][:80] if log['details'] else '-'}"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── Sales Stats ──────────────────────────────────────────────────────────

    @app_commands.command(name="sales", description="[Admin] Statistik penjualan.")
    @app_commands.guild_only()
    async def sales_stats(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # Revenue by day (last 7 days)
        rows = await self.db._execute(
            """
            SELECT DATE(created_at) AS day, COUNT(*) AS orders, SUM(total_price) AS revenue
            FROM orders WHERE status = 'success'
            AND created_at >= DATE('now', '-7 days')
            GROUP BY day ORDER BY day DESC
            """,
            fetch="all",
        )

        top_products = await self.db.get_top_selling_products(5)
        top_customers = await self.db.get_top_customers(5)
        order_stats = await self.db.get_order_stats()

        embed = _base_embed(title="📈 Statistik Penjualan", color=Config.COLOR_GOLD)

        # Revenue summary
        embed.add_field(
            name="💰 Total Revenue",
            value=format_price(order_stats["revenue"]),
            inline=True,
        )
        embed.add_field(
            name="✅ Total Order Sukses",
            value=str(order_stats["success"]),
            inline=True,
        )
        embed.add_field(
            name="👥 Unique Buyers",
            value=str(order_stats["unique_buyers"]),
            inline=True,
        )

        # Last 7 days
        if rows:
            daily_text = "\n".join(
                f"`{r['day']}` — {r['orders']} order | {format_price(r['revenue'] or 0)}"
                for r in rows
            )
            embed.add_field(
                name="📅 Revenue 7 Hari Terakhir",
                value=daily_text or "Tidak ada data",
                inline=False,
            )

        # Top products
        if top_products:
            prod_text = "\n".join(
                f"{i+1}. **{p['name']}** — {p['total_orders']} sales | {format_price(p['total_revenue'] or 0)}"
                for i, p in enumerate(top_products)
            )
            embed.add_field(name="🏆 Top Produk", value=prod_text, inline=False)

        # Top customers
        if top_customers:
            cust_text = "\n".join(
                f"{i+1}. <@{c['user_id']}> — {c['total_orders']} orders | {format_price(c['total_spent'] or 0)}"
                for i, c in enumerate(top_customers)
            )
            embed.add_field(name="👑 Top Pembeli", value=cust_text, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── Admin User Info ──────────────────────────────────────────────────────

    @app_commands.command(name="user-info", description="[Admin] Lihat info pembelian user.")
    @app_commands.guild_only()
    @app_commands.describe(user="Mention user")
    async def user_info(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        orders = await self.db.get_user_orders(user.id, limit=20)
        history = await self.db.get_user_purchase_history(user.id, limit=5)
        tickets = await self.db.get_user_tickets(user.id)

        total_spent = sum(
            o["total_price"] for o in orders if o["status"] == "success"
        )

        embed = _base_embed(
            title=f"👤 Info User — {user.display_name}",
            color=Config.COLOR_INFO,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Discord", value=f"{user} (`{user.id}`)", inline=False)
        embed.add_field(name="Total Order", value=str(len(orders)), inline=True)
        embed.add_field(name="Total Ticket", value=str(len(tickets)), inline=True)
        embed.add_field(name="Total Spent", value=format_price(total_spent), inline=True)

        if history:
            hist_text = "\n".join(
                f"{'✅' if h['status'] == 'success' else '❌'} **{h['product_name']}** — {format_price(h['total_price'])} | {h['created_at'][:10]}"
                for h in history
            )
            embed.add_field(name="📋 Riwayat Terakhir", value=hist_text, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── Auto Backup Task ─────────────────────────────────────────────────────

    @tasks.loop(hours=Config.BACKUP_INTERVAL_HOURS)
    async def auto_backup(self) -> None:
        """Auto-backup database periodically."""
        try:
            import shutil
            import os
            import glob
            from datetime import datetime

            backup_dir = "logs/backups"
            os.makedirs(backup_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            src = Config.DATABASE_PATH
            if not os.path.exists(src):
                return

            dst = f"{backup_dir}/store_{timestamp}.db"
            shutil.copy2(src, dst)

            # Remove old backups beyond max count
            backups = sorted(glob.glob(f"{backup_dir}/store_*.db"))
            max_files = Config.BACKUP_MAX_FILES
            while len(backups) > max_files:
                os.remove(backups.pop(0))

            logger.info(f"Auto-backup completed: {dst}")

            # Notify log channel
            if Config.LOG_CHANNEL_ID:
                channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
                if channel and isinstance(channel, discord.TextChannel):
                    size_kb = os.path.getsize(dst) // 1024
                    await channel.send(
                        embed=success_embed(
                            "🔄 Auto Backup",
                            f"Database berhasil di-backup otomatis.\n💾 `{dst}` ({size_kb} KB)",
                        )
                    )

            await self.db.log_activity(
                action="Auto Backup",
                actor_name="System",
                details=f"Backup: {dst}",
            )
        except Exception as e:
            logger.error(f"Auto backup failed: {e}")

    @auto_backup.before_loop
    async def before_auto_backup(self) -> None:
        await self.bot.wait_until_ready()

    # ─── Sync Command ─────────────────────────────────────────────────────────

    @app_commands.command(name="sync", description="[Owner] Sync slash commands ke Discord.")
    @app_commands.guild_only()
    async def sync_commands(self, interaction: discord.Interaction) -> None:
        if not is_owner(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya owner."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        try:
            guild = discord.Object(id=Config.GUILD_ID)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await interaction.followup.send(
                embed=success_embed(
                    "Commands Synced",
                    f"Berhasil sync **{len(synced)}** slash command ke server ini.",
                ),
                ephemeral=True,
            )
            logger.info(f"Synced {len(synced)} commands by {interaction.user}")
        except Exception as e:
            logger.error(f"Sync error: {e}")
            await interaction.followup.send(
                embed=error_embed("Sync Gagal", str(e)), ephemeral=True
            )

    @app_commands.command(name="ping", description="Cek latensi bot.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        color = (
            Config.COLOR_SUCCESS if latency_ms < 100
            else Config.COLOR_WARNING if latency_ms < 250
            else Config.COLOR_ERROR
        )
        embed = _base_embed(title="🏓 Pong!", color=color)
        embed.add_field(name="Latensi", value=f"`{latency_ms}ms`", inline=True)
        embed.add_field(name="Status", value="🟢 Online", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="admin-help", description="Tampilkan semua command admin.")
    @app_commands.guild_only()
    async def admin_help(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        embed = _base_embed(title="📚 Admin Command Reference", color=Config.COLOR_GOLD)

        commands_map = {
            "🏪 Store": [
                "`/setup-store` — Setup tampilan store utama",
                "`/store-stats` — Statistik lengkap store",
                "`/store-config` — Ubah konfigurasi store",
                "`/backup` — Backup database manual",
            ],
            "📂 Category": [
                "`/category add` — Tambah kategori",
                "`/category edit` — Edit kategori",
                "`/category delete` — Hapus kategori",
                "`/category list` — Daftar kategori",
                "`/category toggle` — Aktif/nonaktif",
            ],
            "🛍️ Product": [
                "`/product add` — Tambah produk",
                "`/product edit` — Edit produk",
                "`/product delete` — Hapus produk",
                "`/product list` — Daftar produk",
                "`/product info` — Detail produk",
                "`/product toggle` — Aktif/nonaktif",
                "`/product set-payments` — Atur payment produk",
            ],
            "📦 Stock": [
                "`/stock add` — Tambah stok (modal)",
                "`/stock add-text` — Tambah stok (text)",
                "`/stock view` — Lihat stok",
                "`/stock remove` — Hapus item stok",
                "`/stock clear` — Clear semua stok",
            ],
            "💳 Payment": [
                "`/payment add` — Tambah payment",
                "`/payment edit` — Edit payment",
                "`/payment delete` — Hapus payment",
                "`/payment list` — Daftar payment",
                "`/payment toggle` — Aktif/nonaktif",
            ],
            "🎟️ Voucher": [
                "`/voucher create` — Buat voucher",
                "`/voucher list` — Daftar voucher",
                "`/voucher delete` — Hapus voucher",
                "`/voucher toggle` — Aktif/nonaktif",
                "`/voucher check` — Cek info voucher",
            ],
            "📋 Order & Ticket": [
                "`/order info` — Detail order",
                "`/order list` — Daftar order",
                "`/order invoice` — Cetak invoice",
                "`/ticket list` — Daftar ticket",
                "`/ticket info` — Info ticket",
                "`/ticket close` — Tutup ticket",
                "`/ticket delete` — Hapus ticket",
            ],
            "📊 Reports": [
                "`/logs` — Log aktivitas",
                "`/sales` — Statistik penjualan",
                "`/user-info` — Info user",
            ],
            "⚙️ System": [
                "`/sync` — Sync slash commands (Owner)",
                "`/ping` — Cek latensi",
            ],
        }

        for category, cmds in commands_map.items():
            embed.add_field(name=category, value="\n".join(cmds), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot, bot.db))
