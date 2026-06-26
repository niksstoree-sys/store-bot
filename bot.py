"""
bot.py — Main Discord Store Bot entry point.
Initializes database, loads all cogs, registers persistent views,
syncs slash commands, and starts the bot.
"""

import asyncio
import logging
import sys
import os

import discord
from discord.ext import commands

from config import Config
from database.database import Database
from utils.logger import setup_logging

# ─── Logging Setup ────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger("store.bot")

# ─── Cogs to Load ─────────────────────────────────────────────────────────────
COGS: list[str] = [
    "cogs.store",
    "cogs.category",
    "cogs.product",
    "cogs.stock",
    "cogs.payment",
    "cogs.order",
    "cogs.ticket",
    "cogs.admin",
    "cogs.variant",
    "cogs.rating",
]


class StoreBot(commands.Bot):
    """
    Main bot class.
    Holds a shared Database instance accessible from all cogs via bot.db.
    """

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix=Config.BOT_PREFIX,
            intents=intents,
            help_command=None,
        )
        self.db: Database = Database(Config.DATABASE_PATH)

    # ─── Setup Hook ───────────────────────────────────────────────────────────

    async def setup_hook(self) -> None:
        """Called once before the bot connects. Initialise DB and load cogs."""
        logger.info("Initializing database...")
        await self.db.initialize()

        logger.info("Loading cogs...")
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info(f"  ✅ Loaded: {cog}")
            except Exception as e:
                logger.error(f"  ❌ Failed to load {cog}: {e}", exc_info=True)

        # ─── Register Persistent Views ─────────────────────────────────────────
        # These must be added BEFORE connecting so Discord can route interactions
        # that come in before on_ready fires.
        from utils.views import TicketActionView
        self.add_view(TicketActionView(self.db))
        logger.info("Persistent views registered.")

        # ─── Register Store View (if categories exist) ─────────────────────────
        categories = await self.db.get_categories(active_only=True)
        if categories:
            from utils.views import StoreMainView
            self.add_view(StoreMainView(categories, self.db))
            logger.info("Store main view registered.")

        # ─── Sync Commands to Guild ────────────────────────────────────────────
        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            try:
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} slash commands to guild {Config.GUILD_ID}.")
            except discord.HTTPException as e:
                logger.error(f"Failed to sync commands: {e}")

    # ─── Events ───────────────────────────────────────────────────────────────

    async def on_ready(self) -> None:
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"  Bot online: {self.user} (ID: {self.user.id})")
        logger.info(f"  Guilds   : {len(self.guilds)}")
        logger.info(f"  Cogs     : {len(self.cogs)}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Set presence
        activity_type_map = {
            "watching": discord.ActivityType.watching,
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "streaming": discord.ActivityType.streaming,
        }
        activity_type = activity_type_map.get(Config.BOT_ACTIVITY, discord.ActivityType.watching)
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=activity_type,
                name=Config.BOT_STATUS,
            ),
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        logger.info(f"Joined guild: {guild.name} ({guild.id})")

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        logger.error(f"Unhandled error in {event_method}:", exc_info=True)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Global error handler for all slash commands."""
        from utils.embeds import error_embed

        logger.error(f"App command error for {interaction.command}: {error}", exc_info=True)

        error_message = "Terjadi kesalahan. Coba lagi nanti."

        if isinstance(error, discord.app_commands.CommandOnCooldown):
            error_message = f"Perintah ini sedang cooldown. Coba lagi dalam {error.retry_after:.1f}s."
        elif isinstance(error, discord.app_commands.MissingPermissions):
            error_message = "Kamu tidak punya permission untuk menjalankan perintah ini."
        elif isinstance(error, discord.app_commands.BotMissingPermissions):
            error_message = f"Bot tidak punya permission: `{', '.join(error.missing_permissions)}`"
        elif isinstance(error, discord.app_commands.NoPrivateMessage):
            error_message = "Perintah ini hanya bisa digunakan di server."
        elif isinstance(error, discord.app_commands.TransformerError):
            error_message = "Input tidak valid. Cek kembali nilai yang kamu masukkan."

        embed = error_embed("Error", error_message)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """
        Intercept select-menu interactions from the persistent store view
        to ensure the DB reference is always fresh (handles bot restarts).
        """
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")

            # Refresh store category select with current DB categories
            if custom_id == "store:category_select":
                from utils.views import StoreCategorySelect
                # Let the registered persistent view handle it normally
                pass

        await super().on_interaction(interaction)


# ─── Entry Point ──────────────────────────────────────────────────────────────

async def main() -> None:
    """Validate config, then start the bot."""
    try:
        Config.validate()
    except EnvironmentError as e:
        logger.critical(f"\n{e}\n\nPastikan kamu sudah mengisi file .env dengan benar.")
        sys.exit(1)

    bot = StoreBot()

    async with bot:
        try:
            await bot.start(Config.TOKEN)
        except discord.LoginFailure:
            logger.critical("Token Discord tidak valid! Cek TOKEN di .env kamu.")
            sys.exit(1)
        except discord.PrivilegedIntentsRequired:
            logger.critical(
                "Privileged Intents belum diaktifkan di Discord Developer Portal!\n"
                "Aktifkan 'SERVER MEMBERS INTENT' dan 'MESSAGE CONTENT INTENT'."
            )
            sys.exit(1)
        except KeyboardInterrupt:
            logger.info("Bot dihentikan oleh user.")


if __name__ == "__main__":
    asyncio.run(main())
