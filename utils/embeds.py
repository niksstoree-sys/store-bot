"""
utils/embeds.py — Centralized embed factory for consistent, professional Discord embeds.
All embeds use Config colors, footer, and timestamp.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional, Any

import discord

from config import Config
from utils.helpers import format_price, truncate


def _base_embed(
    title: str = "",
    description: str = "",
    color: int = Config.COLOR_PRIMARY,
) -> discord.Embed:
    """Create a base embed with standard footer and timestamp."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"⚡ {Config.STORE_NAME}", icon_url=None)
    return embed


# ─── Store Embeds ─────────────────────────────────────────────────────────────

def store_main_embed(settings: dict[str, str]) -> discord.Embed:
    name = settings.get("store_name", Config.STORE_NAME)
    desc = settings.get("store_description", Config.STORE_DESCRIPTION)
    banner = settings.get("store_banner", "")
    thumbnail = settings.get("store_thumbnail", "")

    embed = _base_embed(
        title=f"🏪 {name}",
        description=(
            f"{desc}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📂 **Pilih kategori** di bawah untuk melihat produk.\n"
            "💬 Butuh bantuan? Hubungi admin kami.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=Config.COLOR_PRIMARY,
    )
    if banner:
        embed.set_image(url=banner)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


def product_embed(
    product: sqlite3.Row,
    stock_count: int,
    payments: list[sqlite3.Row],
) -> discord.Embed:
    price_str = format_price(product["price"])
    payment_str = " • ".join(p["name"] for p in payments) if payments else "Tidak ada"
    stock_display = f"**{stock_count}** tersedia" if stock_count > 0 else "❌ Stok habis"

    embed = _base_embed(
        title=f"{product['emoji']} {product['name']}",
        description=truncate(product["description"], 300) or "Tidak ada deskripsi.",
        color=Config.COLOR_PRIMARY if stock_count > 0 else Config.COLOR_ERROR,
    )
    embed.add_field(name="💰 Harga", value=price_str, inline=True)
    embed.add_field(name="📦 Stok", value=stock_display, inline=True)
    embed.add_field(name="💳 Payment", value=payment_str, inline=False)

    if product["thumbnail_url"]:
        embed.set_thumbnail(url=product["thumbnail_url"])
    if product["banner_url"]:
        embed.set_image(url=product["banner_url"])

    embed.set_footer(text=f"⚡ {Config.STORE_NAME} | ID: {product['id']}")
    return embed


# ─── Order Embeds ─────────────────────────────────────────────────────────────

def order_embed(order: sqlite3.Row, product: sqlite3.Row) -> discord.Embed:
    status_map = {
        "pending": ("⏳", "Menunggu Konfirmasi", Config.COLOR_WARNING),
        "success": ("✅", "Berhasil", Config.COLOR_SUCCESS),
        "cancelled": ("❌", "Dibatalkan", Config.COLOR_ERROR),
        "processing": ("🔄", "Diproses", Config.COLOR_INFO),
    }
    emoji, status_text, color = status_map.get(
        order["status"], ("❓", order["status"], Config.COLOR_DARK)
    )

    embed = _base_embed(
        title=f"🧾 Invoice #{order['invoice_number']}",
        color=color,
    )
    embed.add_field(name="📦 Produk", value=product["name"], inline=True)
    embed.add_field(name="💰 Total", value=format_price(order["total_price"]), inline=True)
    embed.add_field(name="💳 Payment", value=order["payment_method"], inline=True)
    embed.add_field(name="📊 Status", value=f"{emoji} {status_text}", inline=True)
    embed.add_field(name="👤 User", value=f"<@{order['user_id']}>", inline=True)
    embed.add_field(name="📅 Waktu", value=order["created_at"], inline=True)

    if order["voucher_code"]:
        embed.add_field(
            name="🎟️ Voucher",
            value=f"`{order['voucher_code']}` (-{format_price(order['discount_amount'])})",
            inline=False,
        )
    if order["notes"]:
        embed.add_field(name="📝 Catatan", value=truncate(order["notes"], 200), inline=False)

    return embed


def order_success_embed(order: sqlite3.Row, stock_content: str) -> discord.Embed:
    embed = _base_embed(
        title="✅ Pembelian Berhasil!",
        description=(
            f"Terima kasih telah berbelanja di **{Config.STORE_NAME}**!\n"
            f"Invoice: `{order['invoice_number']}`"
        ),
        color=Config.COLOR_SUCCESS,
    )
    embed.add_field(name="📦 Produk", value=order["product_name"], inline=True)
    embed.add_field(name="💰 Total", value=format_price(order["total_price"]), inline=True)
    embed.add_field(
        name="🎁 Item Anda",
        value=f"```\n{stock_content}\n```",
        inline=False,
    )
    return embed


def order_cancelled_embed(order: sqlite3.Row, reason: str = "") -> discord.Embed:
    embed = _base_embed(
        title="❌ Pembelian Dibatalkan",
        description=f"Order `{order['invoice_number']}` telah dibatalkan.",
        color=Config.COLOR_ERROR,
    )
    if reason:
        embed.add_field(name="Alasan", value=reason, inline=False)
    return embed


# ─── Ticket Embeds ────────────────────────────────────────────────────────────

def ticket_welcome_embed(user: discord.Member, order: sqlite3.Row, product: sqlite3.Row) -> discord.Embed:
    embed = _base_embed(
        title="🎫 Ticket Pembelian",
        description=(
            f"Halo {user.mention}! 👋\n\n"
            f"Ticket pembelian Anda telah dibuat.\n"
            f"Admin akan segera memproses pesanan Anda.\n\n"
            "**Langkah selanjutnya:**\n"
            "1. Lakukan pembayaran sesuai metode yang dipilih\n"
            "2. Upload bukti pembayaran\n"
            "3. Tunggu konfirmasi dari admin\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=Config.COLOR_INFO,
    )
    embed.add_field(name="📦 Produk", value=product["name"], inline=True)
    embed.add_field(name="💰 Total", value=format_price(order["total_price"]), inline=True)
    embed.add_field(name="💳 Metode", value=order["payment_method"], inline=True)
    embed.add_field(name="🧾 Invoice", value=f"`{order['invoice_number']}`", inline=False)
    return embed


# ─── Admin / Log Embeds ───────────────────────────────────────────────────────

def log_embed(
    action: str,
    actor: str,
    details: str,
    color: int = Config.COLOR_INFO,
) -> discord.Embed:
    embed = _base_embed(title=f"📋 {action}", color=color)
    embed.add_field(name="👤 Actor", value=actor, inline=True)
    embed.add_field(name="📝 Detail", value=truncate(details, 300), inline=False)
    return embed


def stats_embed(stats: dict[str, Any], top_products: list[sqlite3.Row]) -> discord.Embed:
    embed = _base_embed(
        title=f"📊 Statistik {Config.STORE_NAME}",
        color=Config.COLOR_GOLD,
    )
    embed.add_field(name="📂 Kategori", value=format(stats["categories"], ","), inline=True)
    embed.add_field(name="🛍️ Produk", value=format(stats["products"], ","), inline=True)
    embed.add_field(name="📦 Stok Tersedia", value=format(stats["available_stock"], ","), inline=True)
    embed.add_field(name="✅ Order Sukses", value=format(stats["success"], ","), inline=True)
    embed.add_field(name="⏳ Order Pending", value=format(stats["pending"], ","), inline=True)
    embed.add_field(name="👥 Total Pembeli", value=format(stats["unique_buyers"], ","), inline=True)
    embed.add_field(name="💰 Total Revenue", value=format_price(stats["revenue"]), inline=True)
    embed.add_field(name="🎫 Total Ticket", value=format(stats.get("ticket_total", 0), ","), inline=True)
    embed.add_field(name="🟢 Ticket Open", value=format(stats.get("ticket_open", 0), ","), inline=True)

    if top_products:
        top_text = "\n".join(
            f"{i+1}. **{p['name']}** — {p['total_orders']} orders ({format_price(p['total_revenue'] or 0)})"
            for i, p in enumerate(top_products)
        )
        embed.add_field(name="🏆 Top Produk", value=top_text, inline=False)

    return embed


def error_embed(title: str, description: str) -> discord.Embed:
    return _base_embed(title=f"❌ {title}", description=description, color=Config.COLOR_ERROR)


def success_embed(title: str, description: str) -> discord.Embed:
    return _base_embed(title=f"✅ {title}", description=description, color=Config.COLOR_SUCCESS)


def info_embed(title: str, description: str) -> discord.Embed:
    return _base_embed(title=f"ℹ️ {title}", description=description, color=Config.COLOR_INFO)


def warning_embed(title: str, description: str) -> discord.Embed:
    return _base_embed(title=f"⚠️ {title}", description=description, color=Config.COLOR_WARNING)


def product_list_embed(
    products: list[sqlite3.Row],
    stock_counts: dict[int, int],
    category_name: str,
    page: int = 1,
    total_pages: int = 1,
) -> discord.Embed:
    embed = _base_embed(
        title=f"🛍️ Produk — {category_name}",
        color=Config.COLOR_PRIMARY,
    )
    if not products:
        embed.description = "Belum ada produk di kategori ini."
        return embed

    for product in products:
        stock = stock_counts.get(product["id"], 0)
        stock_text = f"Stok: {stock}" if stock > 0 else "Stok: Habis"
        embed.add_field(
            name=f"{product['emoji']} {product['name']}",
            value=f"{format_price(product['price'])} | {stock_text}",
            inline=True,
        )

    if total_pages > 1:
        embed.set_footer(text=f"⚡ {Config.STORE_NAME} | Halaman {page}/{total_pages}")
    return embed


def purchase_history_embed(
    orders: list[sqlite3.Row],
    user: discord.Member,
    page: int,
    total_pages: int,
) -> discord.Embed:
    embed = _base_embed(
        title=f"🛒 Riwayat Pembelian — {user.display_name}",
        color=Config.COLOR_PRIMARY,
    )
    if not orders:
        embed.description = "Belum ada riwayat pembelian."
        return embed

    rows = []
    for o in orders:
        status_emoji = {"success": "✅", "cancelled": "❌", "pending": "⏳"}.get(o["status"], "❓")
        rows.append(
            f"{status_emoji} **{o['product_name']}** — {format_price(o['total_price'])}\n"
            f"   `{o['invoice_number']}` | {o['created_at'][:10]}"
        )
    embed.description = "\n".join(rows)

    if total_pages > 1:
        embed.set_footer(text=f"⚡ {Config.STORE_NAME} | Halaman {page}/{total_pages}")
    return embed


def voucher_list_embed(vouchers: list[sqlite3.Row]) -> discord.Embed:
    embed = _base_embed(title="🎟️ Daftar Voucher", color=Config.COLOR_GOLD)
    if not vouchers:
        embed.description = "Belum ada voucher."
        return embed
    for v in vouchers:
        active = "✅ Aktif" if v["is_active"] else "❌ Nonaktif"
        disc = (
            f"{int(v['discount_value'])}%"
            if v["discount_type"] == "percent"
            else format_price(v["discount_value"])
        )
        uses = f"{v['used_count']}/{v['max_uses']}" if v["max_uses"] > 0 else f"{v['used_count']}/∞"
        embed.add_field(
            name=f"`{v['code']}`",
            value=f"Diskon: {disc} | Pemakaian: {uses} | {active}",
            inline=False,
        )
    return embed


def invoice_embed(order: sqlite3.Row) -> discord.Embed:
    embed = _base_embed(
        title="🧾 Invoice Pembelian",
        description=f"Terima kasih telah berbelanja di **{Config.STORE_NAME}**!",
        color=Config.COLOR_SUCCESS,
    )
    embed.add_field(name="📋 Invoice", value=f"`{order['invoice_number']}`", inline=False)
    embed.add_field(name="📦 Produk", value=order["product_name"], inline=True)
    embed.add_field(name="💰 Total", value=format_price(order["total_price"]), inline=True)
    embed.add_field(name="💳 Payment", value=order["payment_method"], inline=True)
    embed.add_field(name="📅 Tanggal", value=order["created_at"][:16], inline=True)
    embed.add_field(name="✅ Status", value="LUNAS", inline=True)
    return embed
