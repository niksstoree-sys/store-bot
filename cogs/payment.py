"""
cogs/payment.py — Payment method management.
Admin-only: /payment add | edit | delete | list | toggle
"""

import logging

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, _base_embed
from utils.helpers import is_admin, clean_input
from config import Config

logger = logging.getLogger("store.cog.payment")


class PaymentAddModal(ui.Modal, title="💳 Tambah Metode Payment"):
    name = ui.TextInput(label="Nama Payment", max_length=50, placeholder="Dana")
    details = ui.TextInput(
        label="Detail / Nomor Rekening",
        style=discord.TextStyle.paragraph,
        max_length=500,
        placeholder="085xxxxxxxx (Dana)",
    )
    position = ui.TextInput(
        label="Posisi (urutan tampil)", max_length=5, placeholder="1", required=False
    )


class PaymentEditModal(ui.Modal, title="✏️ Edit Metode Payment"):
    name = ui.TextInput(label="Nama Payment", max_length=50)
    details = ui.TextInput(
        label="Detail / Nomor Rekening",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(self, payment, db: Database, on_submit_cb) -> None:
        super().__init__()
        self.payment = payment
        self.db = db
        self._on_submit_cb = on_submit_cb
        self.name.default = payment["name"]
        self.details.default = payment["details"] or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_cb(interaction, self)


class PaymentCog(commands.Cog, name="Payment"):
    """Payment method management commands."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    payment_group = app_commands.Group(
        name="payment", description="Kelola metode pembayaran store."
    )

    # ─── /payment add ─────────────────────────────────────────────────────────

    @payment_group.command(name="add", description="Tambah metode pembayaran baru.")
    @app_commands.guild_only()
    async def payment_add(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        modal = PaymentAddModal()

        async def on_submit(inter: discord.Interaction) -> None:
            name = clean_input(modal.name.value)
            details = clean_input(modal.details.value)
            if not name:
                return await inter.response.send_message(
                    embed=error_embed("Error", "Nama payment tidak boleh kosong."), ephemeral=True
                )
            existing = await self.db.get_payment_by_name(name)
            if existing:
                return await inter.response.send_message(
                    embed=error_embed("Error", f"Payment `{name}` sudah ada."), ephemeral=True
                )
            try:
                pos = int(modal.position.value.strip()) if modal.position.value.strip() else 0
            except ValueError:
                pos = 0

            pay_id = await self.db.create_payment(name=name, details=details, position=pos)
            await inter.response.send_message(
                embed=success_embed(
                    "Payment Ditambahkan",
                    f"💳 **{name}** berhasil ditambahkan! (ID: {pay_id})",
                ),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Payment Added",
                actor_id=inter.user.id,
                actor_name=str(inter.user),
                target=name,
                details=f"ID: {pay_id}",
            )

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    # ─── /payment edit ────────────────────────────────────────────────────────

    @payment_group.command(name="edit", description="Edit metode pembayaran.")
    @app_commands.guild_only()
    @app_commands.describe(payment_id="ID payment")
    async def payment_edit(
        self, interaction: discord.Interaction, payment_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        payment = await self.db.get_payment(payment_id)
        if not payment:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Payment ID `{payment_id}` tidak ditemukan."),
                ephemeral=True,
            )

        async def on_submit(inter: discord.Interaction, modal: PaymentEditModal) -> None:
            name = clean_input(modal.name.value)
            if not name:
                return await inter.response.send_message(
                    embed=error_embed("Error", "Nama tidak boleh kosong."), ephemeral=True
                )
            await self.db.update_payment(
                payment_id,
                name=name,
                details=clean_input(modal.details.value),
            )
            await inter.response.send_message(
                embed=success_embed("Payment Diupdate", f"**{name}** berhasil diupdate."),
                ephemeral=True,
            )
            await self.db.log_activity(
                action="Payment Updated",
                actor_id=inter.user.id,
                actor_name=str(inter.user),
                target=name,
                details=f"ID: {payment_id}",
            )

        modal = PaymentEditModal(payment, self.db, on_submit)
        await interaction.response.send_modal(modal)

    # ─── /payment delete ──────────────────────────────────────────────────────

    @payment_group.command(name="delete", description="Hapus metode pembayaran.")
    @app_commands.guild_only()
    @app_commands.describe(payment_id="ID payment")
    async def payment_delete(
        self, interaction: discord.Interaction, payment_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        payment = await self.db.get_payment(payment_id)
        if not payment:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Payment ID `{payment_id}` tidak ditemukan."),
                ephemeral=True,
            )

        from utils.views import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Konfirmasi",
                description=f"Hapus payment **{payment['name']}**?",
                color=Config.COLOR_WARNING,
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            return await interaction.edit_original_response(
                embed=info_embed("Dibatalkan", "Pembatalan."), view=None
            )

        await self.db.delete_payment(payment_id)
        await interaction.edit_original_response(
            embed=success_embed("Payment Dihapus", f"**{payment['name']}** dihapus."),
            view=None,
        )
        await self.db.log_activity(
            action="Payment Deleted",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=payment["name"],
        )

    # ─── /payment list ────────────────────────────────────────────────────────

    @payment_group.command(name="list", description="Tampilkan semua metode pembayaran.")
    @app_commands.guild_only()
    async def payment_list(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        payments = await self.db.get_payments()

        if not payments:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Belum ada payment."), ephemeral=True
            )

        embed = _base_embed(title="💳 Daftar Payment", color=Config.COLOR_PRIMARY)
        for p in payments:
            status = "✅ Aktif" if p["is_active"] else "❌ Nonaktif"
            embed.add_field(
                name=f"`ID:{p['id']}` {p['name']}",
                value=f"📋 {p['details'][:100] or 'Tidak ada detail'} | {status} | Pos: {p['position']}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /payment toggle ──────────────────────────────────────────────────────

    @payment_group.command(name="toggle", description="Aktif/nonaktifkan metode payment.")
    @app_commands.guild_only()
    @app_commands.describe(payment_id="ID payment")
    async def payment_toggle(
        self, interaction: discord.Interaction, payment_id: int
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        payment = await self.db.get_payment(payment_id)
        if not payment:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Payment ID `{payment_id}` tidak ditemukan."),
                ephemeral=True,
            )

        new_status = 0 if payment["is_active"] else 1
        await self.db.update_payment(payment_id, is_active=new_status)
        await interaction.response.send_message(
            embed=success_embed(
                "Payment Diupdate",
                f"**{payment['name']}** sekarang {'aktif ✅' if new_status else 'nonaktif ❌'}.",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PaymentCog(bot, bot.db))
