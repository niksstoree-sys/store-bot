"""
cogs/ticket.py — Ticket system.
Handles ticket close/delete with HTML transcript generation.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, log_embed, _base_embed
from utils.helpers import is_admin, generate_transcript_html, send_log
from config import Config

logger = logging.getLogger("store.cog.ticket")


async def close_ticket_channel(
    interaction: discord.Interaction, db: Database
) -> None:
    """Mark ticket as closed and lock the channel. Generates a transcript."""
    await interaction.response.defer(ephemeral=True)

    ticket = await db.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        return await interaction.followup.send(
            embed=error_embed("Error", "Channel ini bukan ticket."), ephemeral=True
        )
    if ticket["status"] == "closed":
        return await interaction.followup.send(
            embed=error_embed("Error", "Ticket ini sudah ditutup."), ephemeral=True
        )

    # Only admin or ticket owner can close
    if not is_admin(interaction.user) and interaction.user.id != ticket["user_id"]:
        return await interaction.followup.send(
            embed=error_embed("Akses Ditolak", "Hanya admin atau pemilik ticket."), ephemeral=True
        )

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return

    # ─── Generate Transcript ──────────────────────────────────────────────────
    messages_data: list[dict] = []
    try:
        async for msg in channel.history(limit=500, oldest_first=True):
            messages_data.append({
                "author": str(msg.author),
                "avatar": str(msg.author.display_avatar.url),
                "timestamp": msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "content": msg.content or (
                    f"[{len(msg.embeds)} embed(s)]" if msg.embeds else
                    f"[{len(msg.attachments)} attachment(s)]" if msg.attachments else "[no content]"
                ),
            })
    except discord.Forbidden:
        logger.warning(f"Cannot read history of #{channel.name}")

    ticket_info = {
        "username": ticket["username"],
        "status": "closed",
        "created_at": ticket["created_at"],
        "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    html_content = generate_transcript_html(channel.name, messages_data, ticket_info)
    html_bytes = html_content.encode("utf-8")
    transcript_file = discord.File(
        io.BytesIO(html_bytes),
        filename=f"transcript-{channel.name}.html",
    )

    # ─── Send Transcript to Log Channel ───────────────────────────────────────
    log_channel = interaction.guild.get_channel(Config.LOG_CHANNEL_ID)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        log_emb = log_embed(
            action="🔒 Ticket Ditutup",
            actor=f"{interaction.user} ({interaction.user.id})",
            details=(
                f"Channel: **#{channel.name}**\n"
                f"User: <@{ticket['user_id']}>\n"
                f"Order ID: {ticket['order_id'] or 'N/A'}\n"
                f"Total Messages: {len(messages_data)}"
            ),
            color=Config.COLOR_WARNING,
        )
        try:
            await log_channel.send(embed=log_emb, file=transcript_file)
        except Exception as e:
            logger.warning(f"Failed to send transcript: {e}")

    # ─── Update DB ────────────────────────────────────────────────────────────
    await db.update_ticket(
        ticket["id"],
        status="closed",
        closed_by=interaction.user.id,
        closed_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )

    # ─── Lock Channel ─────────────────────────────────────────────────────────
    try:
        await channel.set_permissions(
            interaction.guild.default_role,
            send_messages=False,
            read_messages=False,
        )
        user_member = interaction.guild.get_member(ticket["user_id"])
        if user_member:
            await channel.set_permissions(user_member, send_messages=False, read_messages=True)

        await channel.send(
            embed=discord.Embed(
                title="🔒 Ticket Ditutup",
                description=(
                    f"Ticket ini telah ditutup oleh {interaction.user.mention}.\n"
                    "Channel akan dihapus dalam 60 detik.\n"
                    "Transcript telah dikirim ke log channel."
                ),
                color=Config.COLOR_WARNING,
                timestamp=datetime.now(timezone.utc),
            )
        )
    except discord.Forbidden:
        pass

    await db.log_activity(
        action="Ticket Closed",
        actor_id=interaction.user.id,
        actor_name=str(interaction.user),
        target=channel.name,
        details=f"Ticket #{ticket['id']} closed. {len(messages_data)} messages.",
        guild_id=interaction.guild_id or 0,
    )

    await interaction.followup.send(
        embed=success_embed("Ticket Ditutup", "Transcript telah dikirim. Channel akan dihapus dalam 60 detik."),
        ephemeral=True,
    )

    # Auto-delete after 60 seconds
    await discord.utils.sleep_until(
        datetime.now(timezone.utc).replace(second=datetime.now().second + 60)
    )
    import asyncio
    await asyncio.sleep(60)
    try:
        await channel.delete(reason=f"Ticket closed by {interaction.user}")
    except Exception:
        pass


async def delete_ticket_channel(
    interaction: discord.Interaction, db: Database
) -> None:
    """Immediately delete a ticket channel (admin only)."""
    if not is_admin(interaction.user):
        return await interaction.response.send_message(
            embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
        )

    ticket = await db.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        return await interaction.response.send_message(
            embed=error_embed("Error", "Channel ini bukan ticket."), ephemeral=True
        )

    from utils.views import ConfirmView
    view = ConfirmView(interaction.user.id, timeout=20)
    await interaction.response.send_message(
        embed=discord.Embed(
            title="⚠️ Hapus Ticket",
            description="Channel ini akan dihapus segera. Lanjutkan?",
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

    channel = interaction.channel
    if isinstance(channel, discord.TextChannel):
        await db.update_ticket(ticket["id"], status="deleted")
        await db.log_activity(
            action="Ticket Deleted",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=channel.name,
            guild_id=interaction.guild_id or 0,
        )
        try:
            await channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except discord.Forbidden:
            await interaction.edit_original_response(
                embed=error_embed("Error", "Bot tidak punya permission hapus channel."), view=None
            )


class TicketCog(commands.Cog, name="Ticket"):
    """Ticket management slash commands."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    ticket_group = app_commands.Group(
        name="ticket", description="Kelola sistem ticket."
    )

    @ticket_group.command(name="list", description="[Admin] Tampilkan semua ticket aktif.")
    @app_commands.guild_only()
    @app_commands.describe(status="Filter status (open/closed)")
    async def ticket_list(
        self,
        interaction: discord.Interaction,
        status: Optional[str] = None,
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # Get all tickets from DB
        query_status = status if status in ("open", "closed") else None
        rows = await self.db._execute(
            "SELECT * FROM tickets"
            + (" WHERE status = ?" if query_status else "")
            + " ORDER BY created_at DESC LIMIT 25",
            (query_status,) if query_status else (),
            fetch="all",
        )

        if not rows:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Tidak ada ticket."), ephemeral=True
            )

        embed = _base_embed(
            title=f"🎫 Daftar Ticket{f' ({status.upper()})' if status else ''}",
            color=Config.COLOR_INFO,
        )
        for t in rows:
            status_emoji = "🟢" if t["status"] == "open" else "🔴"
            channel = interaction.guild.get_channel(t["channel_id"])
            ch_mention = channel.mention if channel else f"#{t['channel_id']} (deleted)"
            embed.add_field(
                name=f"{status_emoji} `#{t['id']}` — {t['username']}",
                value=(
                    f"📌 {ch_mention} | Order: {t['order_id'] or 'N/A'}\n"
                    f"🕐 {t['created_at'][:16]}"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_group.command(name="close", description="Tutup ticket di channel ini.")
    @app_commands.guild_only()
    async def ticket_close(self, interaction: discord.Interaction) -> None:
        await close_ticket_channel(interaction, self.db)

    @ticket_group.command(name="delete", description="[Admin] Hapus ticket channel ini.")
    @app_commands.guild_only()
    async def ticket_delete(self, interaction: discord.Interaction) -> None:
        await delete_ticket_channel(interaction, self.db)

    @ticket_group.command(name="info", description="Lihat info ticket di channel ini.")
    @app_commands.guild_only()
    async def ticket_info(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        ticket = await self.db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            return await interaction.followup.send(
                embed=error_embed("Error", "Channel ini bukan ticket."), ephemeral=True
            )

        order = await self.db.get_order(ticket["order_id"]) if ticket["order_id"] else None
        embed = _base_embed(title="🎫 Info Ticket", color=Config.COLOR_INFO)
        embed.add_field(name="ID", value=str(ticket["id"]), inline=True)
        embed.add_field(name="User", value=f"<@{ticket['user_id']}>", inline=True)
        embed.add_field(name="Status", value=ticket["status"].upper(), inline=True)
        embed.add_field(name="Order ID", value=str(ticket["order_id"] or "N/A"), inline=True)
        embed.add_field(name="Dibuat", value=ticket["created_at"][:16], inline=True)

        if order:
            from utils.helpers import format_price as fp
            embed.add_field(
                name="Order Detail",
                value=(
                    f"Produk: **{order['product_name']}**\n"
                    f"Total: **{format_price(order['total_price'])}**\n"
                    f"Status: **{order['status'].upper()}**\n"
                    f"Invoice: `{order['invoice_number']}`"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_group.command(name="my", description="Lihat ticket milikmu.")
    @app_commands.guild_only()
    async def ticket_my(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        tickets = await self.db.get_user_tickets(interaction.user.id)
        if not tickets:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Kamu belum pernah membuat ticket."), ephemeral=True
            )

        embed = _base_embed(title="🎫 Ticket Kamu", color=Config.COLOR_INFO)
        for t in tickets[:10]:
            status_emoji = "🟢" if t["status"] == "open" else "🔴"
            channel = interaction.guild.get_channel(t["channel_id"])
            ch_mention = channel.mention if channel else "(deleted)"
            embed.add_field(
                name=f"{status_emoji} Ticket #{t['id']}",
                value=f"📌 {ch_mention} | Order: {t['order_id'] or 'N/A'} | {t['created_at'][:10]}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketCog(bot, bot.db))
