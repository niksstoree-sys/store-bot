"""
cogs/rating.py — Rating & review system.
User beri rating setelah order sukses. Rating dikirim ke channel khusus.
"""

import logging
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, _base_embed
from utils.helpers import is_admin, format_price
from config import Config

logger = logging.getLogger("store.cog.rating")

STAR_MAP = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}
COLOR_MAP = {1: Config.COLOR_ERROR, 2: 0xFF6B35, 3: Config.COLOR_WARNING, 4: 0x90EE90, 5: Config.COLOR_SUCCESS}


class RatingModal(ui.Modal, title="⭐ Beri Rating & Review"):
    rating = ui.TextInput(
        label="Rating (1-5)",
        max_length=1,
        placeholder="5",
    )
    review = ui.TextInput(
        label="Review (opsional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
        placeholder="Produk bagus, pengiriman cepat!",
    )

    def __init__(self, order, db: Database) -> None:
        super().__init__()
        self.order = order
        self.db = db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            rating_val = int(self.rating.value.strip())
            if rating_val < 1 or rating_val > 5:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Rating Tidak Valid", "Rating harus angka 1-5."),
                ephemeral=True,
            )

        # Check sudah pernah rating
        existing = await self.db.get_rating_by_order(self.order["id"])
        if existing:
            return await interaction.response.send_message(
                embed=error_embed("Sudah Dirating", "Kamu sudah memberi rating untuk order ini."),
                ephemeral=True,
            )

        review_text = self.review.value.strip() if self.review.value else ""
        variant_name = self.order.get("variant_name", "") or ""

        rating_id = await self.db.create_rating(
            order_id=self.order["id"],
            user_id=interaction.user.id,
            username=str(interaction.user),
            product_id=self.order["product_id"],
            product_name=self.order["product_name"],
            variant_name=variant_name,
            rating=rating_val,
            review=review_text,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Rating Terkirim!",
                f"Terima kasih atas review kamu! {STAR_MAP[rating_val]}",
            ),
            ephemeral=True,
        )

        # Kirim ke rating channel
        await send_rating_to_channel(interaction, self.db, self.order, interaction.user, rating_val, review_text, variant_name)

        await self.db.log_activity(
            action="Rating Submitted",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=self.order["product_name"],
            details=f"Rating: {rating_val}/5",
        )


async def send_rating_to_channel(
    interaction: discord.Interaction,
    db: Database,
    order,
    user: discord.Member,
    rating_val: int,
    review: str,
    variant_name: str = "",
) -> None:
    """Kirim embed rating ke channel yang dikonfigurasi."""
    rating_channel_id = await db.get_setting("rating_channel_id")
    if not rating_channel_id or rating_channel_id == "0":
        return

    try:
        channel_id = int(rating_channel_id)
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        avg_rating = await db.get_product_avg_rating(order["product_id"])
        total_ratings_row = await db._execute(
            "SELECT COUNT(*) AS cnt FROM ratings WHERE product_id = ?",
            (order["product_id"],), fetch="one"
        )
        total_ratings = total_ratings_row["cnt"] if total_ratings_row else 0

        color = COLOR_MAP.get(rating_val, Config.COLOR_PRIMARY)
        stars = STAR_MAP[rating_val]

        embed = discord.Embed(
            title=f"{stars} Review Baru!",
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        # User info
        embed.set_author(
            name=f"{user.display_name} ({user})",
            icon_url=user.display_avatar.url,
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        # Produk info
        product_text = order["product_name"]
        if variant_name:
            product_text += f" — {variant_name}"
        embed.add_field(name="🛍️ Produk", value=product_text, inline=True)
        embed.add_field(name="⭐ Rating", value=f"**{stars}** ({rating_val}/5)", inline=True)
        embed.add_field(name="💰 Total Bayar", value=format_price(order["total_price"]), inline=True)

        if review:
            embed.add_field(name="💬 Review", value=f"*\"{review}\"*", inline=False)

        # Statistik produk
        embed.add_field(
            name="📊 Statistik Produk",
            value=f"Rating rata-rata: **{avg_rating}/5** ({total_ratings} review)",
            inline=False,
        )

        embed.add_field(name="🧾 Invoice", value=f"`{order['invoice_number']}`", inline=True)
        embed.add_field(name="👤 User ID", value=f"`{user.id}`", inline=True)

        embed.set_footer(text=f"⚡ {Config.STORE_NAME} Rating System")

        await channel.send(embed=embed)

    except Exception as e:
        logger.error(f"Failed to send rating to channel: {e}")


class RatingView(ui.View):
    """View dengan tombol rating yang dikirim ke user setelah order sukses."""

    def __init__(self, order, db: Database) -> None:
        super().__init__(timeout=86400)  # 24 jam
        self.order = order
        self.db = db

    @ui.button(label="⭐ Beri Rating", style=discord.ButtonStyle.primary)
    async def give_rating(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.order["user_id"]:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Bukan order kamu."), ephemeral=True
            )
        existing = await self.db.get_rating_by_order(self.order["id"])
        if existing:
            return await interaction.response.send_message(
                embed=error_embed("Sudah Dirating", "Kamu sudah memberi rating untuk order ini."),
                ephemeral=True,
            )
        modal = RatingModal(self.order, self.db)
        await interaction.response.send_modal(modal)


class RatingCog(commands.Cog, name="Rating"):
    """Rating and review system."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    rating_group = app_commands.Group(
        name="rating", description="Kelola sistem rating."
    )

    @rating_group.command(name="set-channel", description="[Admin] Set channel untuk tampilkan rating.")
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel tujuan rating")
    async def set_rating_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        await self.db.set_setting("rating_channel_id", str(channel.id))
        await interaction.response.send_message(
            embed=success_embed(
                "Channel Rating Set",
                f"Rating akan dikirim ke {channel.mention}",
            ),
            ephemeral=True,
        )

    @rating_group.command(name="list", description="Lihat rating produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def rating_list(self, interaction: discord.Interaction, product_id: int) -> None:
        await interaction.response.defer(ephemeral=True)

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.followup.send(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."), ephemeral=True
            )

        ratings = await self.db.get_product_ratings(product_id, limit=10)
        avg = await self.db.get_product_avg_rating(product_id)

        embed = _base_embed(
            title=f"⭐ Rating — {product['name']}",
            description=f"Rating rata-rata: **{avg}/5** ({len(ratings)} review)",
            color=Config.COLOR_GOLD,
        )

        if not ratings:
            embed.description = "Belum ada rating untuk produk ini."
        else:
            for r in ratings[:8]:
                stars = STAR_MAP.get(r["rating"], "⭐")
                review_text = f"\n*\"{r['review']}\"*" if r["review"] else ""
                embed.add_field(
                    name=f"{stars} {r['username']}",
                    value=f"{r['variant_name'] or product['name']}{review_text}\n`{r['created_at'][:10]}`",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @rating_group.command(name="recent", description="[Admin] Lihat rating terbaru semua produk.")
    @app_commands.guild_only()
    async def rating_recent(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        ratings = await self.db.get_recent_ratings(limit=15)
        embed = _base_embed(title="⭐ Rating Terbaru", color=Config.COLOR_GOLD)

        if not ratings:
            embed.description = "Belum ada rating."
        else:
            for r in ratings:
                stars = STAR_MAP.get(r["rating"], "⭐")
                embed.add_field(
                    name=f"{stars} {r['username']} — {r['product_name']}",
                    value=f"{r['review'][:80] if r['review'] else 'Tidak ada review'} | `{r['created_at'][:10]}`",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RatingCog(bot, bot.db))
