"""
cogs/order.py — Order processing system v2.
Update dari v1: support variant, payment proof wajib, rating setelah beli.
REPLACE file cogs/order.py yang lama dengan file ini.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database.database import Database
from utils.embeds import (
    order_embed, order_success_embed, order_cancelled_embed,
    invoice_embed, error_embed, success_embed, info_embed, log_embed,
)
from utils.helpers import (
    is_admin, format_price, safe_send_dm, send_log,
)
from utils.views import TicketActionView
from config import Config

logger = logging.getLogger("store.cog.order")


async def _create_ticket_channel(
    interaction: discord.Interaction,
    db: Database,
    order_id: int,
    product_name: str,
    user: discord.Member,
) -> Optional[discord.TextChannel]:
    """Helper: buat ticket channel untuk order."""
    guild = interaction.guild
    category_channel = guild.get_channel(Config.TICKET_CATEGORY_ID) if Config.TICKET_CATEGORY_ID else None

    safe_username = "".join(c for c in user.display_name if c.isalnum() or c in "-_")[:20] or "user"
    ticket_name = f"ticket-{safe_username}-{order_id}"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True,
            attach_files=True, embed_links=True,
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True, send_messages=True,
            manage_channels=True, manage_messages=True,
        ),
    }
    admin_role = guild.get_role(Config.ADMIN_ROLE_ID)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_messages=True,
        )

    try:
        ticket_channel = await guild.create_text_channel(
            name=ticket_name,
            category=category_channel,
            overwrites=overwrites,
            topic=f"Order #{order_id} | {user} | {product_name}",
            reason=f"Store ticket for order #{order_id}",
        )
        return ticket_channel
    except discord.Forbidden:
        return None


async def _send_ticket_welcome(
    ticket_channel: discord.TextChannel,
    db: Database,
    user: discord.Member,
    order,
    product,
    payment,
    variant=None,
    discount_amount: float = 0.0,
    voucher_code: str = "",
    customer_info: dict | None = None,
) -> None:
    """Kirim welcome embed + payment info + customer info + bukti pembayaran button ke ticket."""
    from utils.embeds import ticket_welcome_embed
    from utils.views import PaymentProofView

    ticket_embed_msg = ticket_welcome_embed(user, order, product)

    variant_text = f"\n**Tipe:** {variant['name']}" if variant else ""
    payment_info_embed = discord.Embed(
        title="💳 Informasi Pembayaran",
        description=(
            f"**Metode:** {payment['name']}\n"
            f"**Detail:**\n```\n{payment['details'] or 'Hubungi admin untuk detail.'}\n```\n"
            f"**Total:** {format_price(order['total_price'])}{variant_text}"
            + (f"\n\n🎟️ Voucher `{voucher_code.upper()}` diaplikasikan: -**{format_price(discount_amount)}**" if voucher_code else "")
        ),
        color=Config.COLOR_INFO,
    )

    embeds_to_send = [ticket_embed_msg, payment_info_embed]

    # ── Customer Info Embed — hanya kirim jika ada data yang diisi ────────────
    info = customer_info or {}
    if info:
        customer_embed = discord.Embed(
            title="👤 Data Customer",
            color=Config.COLOR_PRIMARY,
        )
        for label, value in info.items():
            display = f"```{value}```" if value else "*tidak diisi*"
            customer_embed.add_field(name=label, value=display, inline=False)
        customer_embed.set_footer(
            text="⚠️ Data ini bersifat rahasia — jangan dibagikan ke pihak lain."
        )
        embeds_to_send.append(customer_embed)

    ticket_view = TicketActionView(db)
    proof_view = PaymentProofView(order["id"], db)

    await ticket_channel.send(
        content=f"🎫 {user.mention} | Ticket Pembelian",
        embeds=embeds_to_send,
        view=ticket_view,
    )
    await ticket_channel.send(
        content="📸 **Langkah selanjutnya:** Upload bukti pembayaran kamu!",
        view=proof_view,
    )


async def process_purchase(
    interaction: discord.Interaction,
    db: Database,
    product,
    payment,
    voucher_code: str = "",
    notes: str = "",
    customer_info: dict | None = None,
) -> None:
    """Purchase flow untuk produk TANPA varian."""
    await interaction.response.defer(ephemeral=True)

    # Cek varian — kalau ada, redirect ke variant flow
    variants = await db.get_product_variants(product["id"])
    if variants:
        from utils.views import VariantSelectView
        payments = await db.get_product_payments(product["id"])
        view = VariantSelectView(product, variants, payments, db)
        return await interaction.followup.send(
            content="🎛️ Produk ini punya beberapa tipe, pilih dulu:",
            view=view, ephemeral=True,
        )

    # Stock check
    stock_count = await db.get_product_stock_count(product["id"])
    if stock_count == 0:
        return await interaction.followup.send(
            embed=error_embed("Stok Habis", "Maaf, produk ini sedang kehabisan stok."), ephemeral=True
        )

    # Voucher validation
    discount_amount, final_price, voucher_row = await _validate_voucher(
        db, voucher_code, product["price"], interaction.user.id
    )
    if voucher_row is False:
        return await interaction.followup.send(
            embed=error_embed("Voucher Error", discount_amount), ephemeral=True
        )

    order_id = await db.create_order(
        user_id=interaction.user.id,
        username=str(interaction.user),
        product_id=product["id"],
        product_name=product["name"],
        total_price=final_price,
        payment_method=payment["name"],
        voucher_code=voucher_code.upper() if voucher_code else "",
        discount_amount=discount_amount,
        notes=notes,
    )
    order = await db.get_order(order_id)

    ticket_channel = await _create_ticket_channel(interaction, db, order_id, product["name"], interaction.user)
    if not ticket_channel:
        await db.update_order(order_id, status="cancelled")
        return await interaction.followup.send(
            embed=error_embed("Error", "Bot tidak bisa membuat ticket channel."), ephemeral=True
        )

    await db.create_ticket(ticket_channel.id, interaction.user.id, str(interaction.user), order_id)
    await db.update_order(order_id, ticket_channel=ticket_channel.id)

    if voucher_row and voucher_row is not False:
        await db.use_voucher(voucher_row["id"], interaction.user.id, order_id)

    await _send_ticket_welcome(
        ticket_channel, db, interaction.user, order, product, payment,
        discount_amount=discount_amount,
        voucher_code=voucher_code,
        customer_info=customer_info,
    )

    await interaction.followup.send(
        embed=success_embed(
            "Ticket Dibuat!",
            f"Ticket pembelianmu di {ticket_channel.mention}!\n\n"
            f"📦 **{product['name']}** — {format_price(final_price)}\n"
            f"💳 **{payment['name']}**\n\n"
            "Upload bukti pembayaran di ticket setelah transfer!",
        ),
        ephemeral=True,
    )

    await db.log_activity(
        action="Order Created",
        actor_id=interaction.user.id, actor_name=str(interaction.user),
        target=product["name"],
        details=f"Order #{order_id} | Total: {format_price(final_price)}",
        guild_id=interaction.guild_id or 0,
    )
    logger.info(f"Order #{order_id} created for {interaction.user}")


async def process_purchase_variant(
    interaction: discord.Interaction,
    db: Database,
    product,
    variant,
    payment,
    voucher_code: str = "",
    notes: str = "",
    customer_info: dict | None = None,
) -> None:
    """Purchase flow untuk produk DENGAN varian."""
    await interaction.response.defer(ephemeral=True)

    # Stock check untuk varian
    stock_count = await db.get_stock_count_by_variant(product["id"], variant["id"])
    if stock_count == 0:
        return await interaction.followup.send(
            embed=error_embed("Stok Habis", f"Varian **{variant['name']}** sedang kehabisan stok."),
            ephemeral=True,
        )

    # Voucher validation pakai harga varian
    discount_amount, final_price, voucher_row = await _validate_voucher(
        db, voucher_code, variant["price"], interaction.user.id
    )
    if voucher_row is False:
        return await interaction.followup.send(
            embed=error_embed("Voucher Error", discount_amount), ephemeral=True
        )

    order_id = await db.create_order(
        user_id=interaction.user.id,
        username=str(interaction.user),
        product_id=product["id"],
        product_name=product["name"],
        total_price=final_price,
        payment_method=payment["name"],
        voucher_code=voucher_code.upper() if voucher_code else "",
        discount_amount=discount_amount,
        notes=notes,
    )
    # Simpan variant info ke order
    await db.update_order(order_id, variant_id=variant["id"], variant_name=variant["name"])
    order = await db.get_order(order_id)

    ticket_channel = await _create_ticket_channel(interaction, db, order_id, product["name"], interaction.user)
    if not ticket_channel:
        await db.update_order(order_id, status="cancelled")
        return await interaction.followup.send(
            embed=error_embed("Error", "Bot tidak bisa membuat ticket channel."), ephemeral=True
        )

    await db.create_ticket(ticket_channel.id, interaction.user.id, str(interaction.user), order_id)
    await db.update_order(order_id, ticket_channel=ticket_channel.id)

    if voucher_row and voucher_row is not False:
        await db.use_voucher(voucher_row["id"], interaction.user.id, order_id)

    await _send_ticket_welcome(
        ticket_channel, db, interaction.user, order, product, payment,
        variant=variant,
        discount_amount=discount_amount,
        voucher_code=voucher_code,
        customer_info=customer_info,
    )

    await interaction.followup.send(
        embed=success_embed(
            "Ticket Dibuat!",
            f"Ticket pembelianmu di {ticket_channel.mention}!\n\n"
            f"📦 **{product['name']}** — {variant['name']}\n"
            f"💰 {format_price(final_price)} | 💳 {payment['name']}\n\n"
            "Upload bukti pembayaran di ticket setelah transfer!",
        ),
        ephemeral=True,
    )

    await db.log_activity(
        action="Order Created (Variant)",
        actor_id=interaction.user.id, actor_name=str(interaction.user),
        target=f"{product['name']} — {variant['name']}",
        details=f"Order #{order_id} | Total: {format_price(final_price)}",
        guild_id=interaction.guild_id or 0,
    )
    logger.info(f"Order #{order_id} (variant: {variant['name']}) created for {interaction.user}")


async def _validate_voucher(db: Database, voucher_code: str, base_price: float, user_id: int):
    """
    Returns (discount_amount, final_price, voucher_row)
    Returns (error_message, 0, False) on error.
    """
    if not voucher_code:
        return 0.0, base_price, None

    voucher_row = await db.get_voucher(voucher_code)
    if not voucher_row:
        return "Kode voucher tidak ditemukan atau sudah expired.", 0, False
    if voucher_row["max_uses"] > 0 and voucher_row["used_count"] >= voucher_row["max_uses"]:
        return "Voucher ini sudah mencapai batas pemakaian.", 0, False
    if await db.user_used_voucher(voucher_row["id"], user_id):
        return "Kamu sudah pernah memakai voucher ini.", 0, False
    if base_price < voucher_row["min_purchase"]:
        return f"Minimum pembelian {format_price(voucher_row['min_purchase'])}.", 0, False

    if voucher_row["discount_type"] == "percent":
        discount = base_price * (voucher_row["discount_value"] / 100)
    else:
        discount = min(voucher_row["discount_value"], base_price)

    final_price = max(0.0, base_price - discount)
    return discount, final_price, voucher_row


async def confirm_order_in_ticket(interaction: discord.Interaction, db: Database) -> None:
    """Admin konfirmasi order — kirim stok via DM + tombol rating."""
    await interaction.response.defer(ephemeral=True)

    ticket = await db.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        return await interaction.followup.send(
            embed=error_embed("Error", "Data ticket tidak ditemukan."), ephemeral=True
        )
    if ticket["status"] != "open":
        return await interaction.followup.send(
            embed=error_embed("Error", "Ticket ini sudah ditutup."), ephemeral=True
        )

    order = await db.get_order(ticket["order_id"])
    if not order:
        return await interaction.followup.send(
            embed=error_embed("Error", "Data order tidak ditemukan."), ephemeral=True
        )
    if order["status"] != "pending":
        return await interaction.followup.send(
            embed=error_embed("Error", f"Order sudah berstatus `{order['status']}`."), ephemeral=True
        )

    # Ambil stok — cek variant_id
    variant_id = order.get("variant_id") or 0
    if variant_id and variant_id > 0:
        stock = await db.get_next_stock(order["product_id"], variant_id=variant_id)
    else:
        stock = await db.get_next_stock(order["product_id"])

    if not stock:
        return await interaction.followup.send(
            embed=error_embed("Stok Habis!", "Tidak ada stok tersedia. Tambah stok dulu."), ephemeral=True
        )

    await db.mark_stock_sold(stock["id"], order["id"])
    await db.update_order(order["id"], status="success", stock_content=stock["content"])
    await db.add_purchase_history(
        user_id=order["user_id"], username=order["username"],
        order_id=order["id"], product_id=order["product_id"],
        product_name=order["product_name"], total_price=order["total_price"],
        status="success",
    )

    # Assign role jika ada
    product = await db.get_product(order["product_id"])
    if product and product["role_id"]:
        member = interaction.guild.get_member(order["user_id"])
        if member:
            role = interaction.guild.get_role(product["role_id"])
            if role:
                try:
                    await member.add_roles(role, reason=f"Purchase #{order['id']}")
                except discord.Forbidden:
                    pass

    updated_order = await db.get_order(order["id"])
    success_embed_msg = order_success_embed(updated_order, stock["content"])
    inv_embed = invoice_embed(updated_order)

    # Tombol Rating
    from cogs.rating import RatingView
    rating_view = RatingView(updated_order, db)
    rating_embed = discord.Embed(
        title="⭐ Beri Rating!",
        description=(
            "Terima kasih sudah berbelanja!\n"
            "Bantulah kami dengan memberikan rating dan review untuk produk ini."
        ),
        color=Config.COLOR_GOLD,
    )

    # Kirim via DM
    buyer = interaction.guild.get_member(order["user_id"])
    dm_sent = False
    if buyer:
        dm_sent = await safe_send_dm(buyer, embeds=[success_embed_msg, inv_embed, rating_embed], view=rating_view)

    # Kirim di ticket jika DM gagal
    channel = interaction.channel
    if isinstance(channel, discord.TextChannel):
        mention = f"<@{order['user_id']}>"
        if not dm_sent:
            await channel.send(
                content=f"📬 {mention} DM kamu tertutup. Item dikirim di sini:",
                embeds=[success_embed_msg, inv_embed, rating_embed],
                view=rating_view,
            )
        else:
            await channel.send(
                content=f"✅ {mention} Pembelian berhasil! Cek DM untuk item dan berikan rating ya!",
                embed=discord.Embed(
                    title="✅ Order Dikonfirmasi",
                    description=f"Order `{updated_order['invoice_number']}` dikonfirmasi oleh {interaction.user.mention}.",
                    color=Config.COLOR_SUCCESS,
                ),
            )

    await db.log_activity(
        action="Order Success",
        actor_id=interaction.user.id, actor_name=str(interaction.user),
        target=order["product_name"],
        details=f"Order #{order['id']} | Invoice: {updated_order['invoice_number']}",
        guild_id=interaction.guild_id or 0,
    )

    log = log_embed(
        action="✅ Order Sukses",
        actor=f"{interaction.user} (Admin)",
        details=(
            f"Order **#{order['id']}** dikonfirmasi.\n"
            f"Buyer: <@{order['user_id']}>\n"
            f"Produk: **{order['product_name']}**"
            + (f" — {order.get('variant_name', '')}" if order.get('variant_name') else "") +
            f"\nTotal: **{format_price(order['total_price'])}**\n"
            f"DM: {'✅' if dm_sent else '❌ dikirim di ticket'}"
        ),
        color=Config.COLOR_SUCCESS,
    )
    await send_log(interaction.client, log, Config.LOG_WEBHOOK_URL or None)

    await interaction.followup.send(
        embed=success_embed("Order Dikonfirmasi", f"Stok terkirim dan rating request dikirim ke user."),
        ephemeral=True,
    )
    logger.info(f"Order #{order['id']} confirmed by {interaction.user}")


async def cancel_order_in_ticket(interaction: discord.Interaction, db: Database) -> None:
    """Admin batalkan order di ticket."""
    await interaction.response.defer(ephemeral=True)

    ticket = await db.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        return await interaction.followup.send(
            embed=error_embed("Error", "Data ticket tidak ditemukan."), ephemeral=True
        )

    order = await db.get_order(ticket["order_id"])
    if not order:
        return await interaction.followup.send(
            embed=error_embed("Error", "Data order tidak ditemukan."), ephemeral=True
        )
    if order["status"] != "pending":
        return await interaction.followup.send(
            embed=error_embed("Error", f"Order sudah berstatus `{order['status']}`."), ephemeral=True
        )

    await db.update_order(order["id"], status="cancelled")
    await db.add_purchase_history(
        user_id=order["user_id"], username=order["username"],
        order_id=order["id"], product_id=order["product_id"],
        product_name=order["product_name"], total_price=order["total_price"],
        status="cancelled",
    )

    updated_order = await db.get_order(order["id"])
    cancel_embed = order_cancelled_embed(updated_order, reason=f"Dibatalkan oleh {interaction.user}")

    channel = interaction.channel
    if isinstance(channel, discord.TextChannel):
        await channel.send(content=f"❌ <@{order['user_id']}> Order kamu dibatalkan.", embed=cancel_embed)

    buyer = interaction.guild.get_member(order["user_id"])
    if buyer:
        await safe_send_dm(buyer, embed=cancel_embed)

    await db.log_activity(
        action="Order Cancelled",
        actor_id=interaction.user.id, actor_name=str(interaction.user),
        target=order["product_name"],
        details=f"Order #{order['id']} cancelled",
        guild_id=interaction.guild_id or 0,
    )

    await interaction.followup.send(
        embed=success_embed("Order Dibatalkan", f"Order `{updated_order['invoice_number']}` dibatalkan."),
        ephemeral=True,
    )


class OrderCog(commands.Cog, name="Order"):
    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    order_group = app_commands.Group(name="order", description="Kelola order di store.")

    @order_group.command(name="info", description="Lihat detail order berdasarkan invoice.")
    @app_commands.guild_only()
    @app_commands.describe(invoice="Nomor invoice")
    async def order_info(self, interaction: discord.Interaction, invoice: str) -> None:
        await interaction.response.defer(ephemeral=True)
        order = await self.db.get_order_by_invoice(invoice.upper())
        if not order:
            return await interaction.followup.send(
                embed=error_embed("Tidak Ditemukan", f"Invoice `{invoice}` tidak ditemukan."), ephemeral=True
            )
        if not is_admin(interaction.user) and order["user_id"] != interaction.user.id:
            return await interaction.followup.send(
                embed=error_embed("Akses Ditolak", "Kamu tidak punya akses ke order ini."), ephemeral=True
            )
        product = await self.db.get_product(order["product_id"])
        if not product:
            return await interaction.followup.send(
                embed=error_embed("Error", "Data produk tidak ditemukan."), ephemeral=True
            )
        embed = order_embed(order, product)
        if order.get("variant_name"):
            embed.add_field(name="🎛️ Varian", value=order["variant_name"], inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @order_group.command(name="list", description="[Admin] Lihat daftar order.")
    @app_commands.guild_only()
    @app_commands.describe(status="Filter status (pending/success/cancelled)", limit="Jumlah order")
    async def order_list(self, interaction: discord.Interaction, status: Optional[str] = None, limit: int = 10) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        limit = max(1, min(limit, 50))
        orders = await self.db.get_orders(status=status, limit=limit)
        if not orders:
            return await interaction.followup.send(
                embed=info_embed("Kosong", "Tidak ada order."), ephemeral=True
            )
        from utils.embeds import _base_embed
        embed = _base_embed(title=f"📋 Daftar Order", color=Config.COLOR_PRIMARY)
        status_emoji = {"pending": "⏳", "success": "✅", "cancelled": "❌"}
        for o in orders[:20]:
            emoji = status_emoji.get(o["status"], "❓")
            variant_text = f" ({o['variant_name']})" if o.get("variant_name") else ""
            embed.add_field(
                name=f"{emoji} `{o['invoice_number']}`",
                value=f"👤 {o['username']} | 📦 {o['product_name']}{variant_text}\n💰 {format_price(o['total_price'])} | {o['created_at'][:16]}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @order_group.command(name="invoice", description="Cetak ulang invoice order.")
    @app_commands.guild_only()
    @app_commands.describe(invoice="Nomor invoice")
    async def order_invoice(self, interaction: discord.Interaction, invoice: str) -> None:
        await interaction.response.defer(ephemeral=True)
        order = await self.db.get_order_by_invoice(invoice.upper())
        if not order:
            return await interaction.followup.send(
                embed=error_embed("Tidak Ditemukan", f"Invoice `{invoice}` tidak ditemukan."), ephemeral=True
            )
        if not is_admin(interaction.user) and order["user_id"] != interaction.user.id:
            return await interaction.followup.send(
                embed=error_embed("Akses Ditolak", "Kamu tidak punya akses."), ephemeral=True
            )
        if order["status"] != "success":
            return await interaction.followup.send(
                embed=error_embed("Error", "Invoice hanya tersedia untuk order sukses."), ephemeral=True
            )
        await interaction.followup.send(embed=invoice_embed(order), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderCog(bot, bot.db))
