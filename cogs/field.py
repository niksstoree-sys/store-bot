"""
cogs/field.py — Product required fields management.
Admin set field apa yang harus diisi user saat beli.
Contoh: Username Roblox, User ID + Zone ID, Player ID, Email, dll.
"""

import logging
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.database import Database
from utils.embeds import success_embed, error_embed, info_embed, _base_embed
from utils.helpers import is_admin, clean_input
from config import Config

logger = logging.getLogger("store.cog.field")


class FieldCog(commands.Cog, name="Field"):
    """Product required fields management."""

    def __init__(self, bot: commands.Bot, db: Database) -> None:
        self.bot = bot
        self.db = db

    field_group = app_commands.Group(
        name="field", description="Kelola field yang wajib diisi user saat beli."
    )

    @field_group.command(name="add", description="Tambah field yang wajib diisi user saat beli produk.")
    @app_commands.guild_only()
    @app_commands.describe(
        product_id="ID produk",
        field_label="Label field yang ditampilkan ke user (contoh: Username Roblox)",
        placeholder="Contoh isian (contoh: NamaUser123)",
        is_required="Wajib diisi atau tidak (default: Ya)",
        position="Urutan field (1, 2, 3, dst)",
    )
    async def field_add(
        self,
        interaction: discord.Interaction,
        product_id: int,
        field_label: str,
        placeholder: str = "",
        is_required: bool = True,
        position: int = 0,
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

        label = clean_input(field_label)
        if not label:
            return await interaction.response.send_message(
                embed=error_embed("Error", "Label field tidak boleh kosong."), ephemeral=True
            )

        # field_name = slugified version of label
        field_name = label.lower().replace(" ", "_")[:50]

        field_id = await self.db.create_product_field(
            product_id=product_id,
            field_name=field_name,
            field_label=label,
            placeholder=clean_input(placeholder),
            is_required=1 if is_required else 0,
            position=position,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Field Ditambahkan",
                f"Field **{label}** berhasil ditambahkan ke produk **{product['name']}**!\n"
                f"{'✅ Wajib diisi' if is_required else '⚪ Opsional'}"
                + (f"\n📝 Placeholder: `{placeholder}`" if placeholder else ""),
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Field Added",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=product["name"],
            details=f"Field: {label}",
        )

    @field_group.command(name="list", description="Tampilkan field yang harus diisi user untuk produk ini.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def field_list(self, interaction: discord.Interaction, product_id: int) -> None:
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

        fields = await self.db.get_product_fields(product_id)
        if not fields:
            return await interaction.followup.send(
                embed=info_embed(
                    "Tidak Ada Field",
                    f"Produk **{product['name']}** belum punya required field.\n"
                    f"Tambahkan dengan `/field add product_id:{product_id} field_label:Username Roblox`",
                ),
                ephemeral=True,
            )

        embed = _base_embed(
            title=f"📋 Required Fields — {product['name']}",
            description=f"User harus mengisi {len(fields)} field saat membeli produk ini.",
            color=Config.COLOR_INFO,
        )
        for f in fields:
            required_text = "✅ Wajib" if f["is_required"] else "⚪ Opsional"
            placeholder_text = f"\n📝 Placeholder: `{f['placeholder']}`" if f["placeholder"] else ""
            embed.add_field(
                name=f"`ID:{f['id']}` #{f['position']} — {f['field_label']}",
                value=f"{required_text}{placeholder_text}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @field_group.command(name="delete", description="Hapus field dari produk.")
    @app_commands.guild_only()
    @app_commands.describe(field_id="ID field yang ingin dihapus (lihat dengan /field list)")
    async def field_delete(self, interaction: discord.Interaction, field_id: int) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed("Akses Ditolak", "Hanya admin."), ephemeral=True
            )

        result = await self.db.delete_product_field(field_id)
        if result == 0:
            return await interaction.response.send_message(
                embed=error_embed("Error", f"Field ID `{field_id}` tidak ditemukan."),
                ephemeral=True,
            )

        await interaction.response.send_message(
            embed=success_embed("Field Dihapus", f"Field ID `{field_id}` berhasil dihapus."),
            ephemeral=True,
        )

    @field_group.command(name="clear", description="Hapus SEMUA field dari produk.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def field_clear(self, interaction: discord.Interaction, product_id: int) -> None:
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

        from utils.views import ConfirmView
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Hapus Semua Field",
                description=f"Hapus semua required field dari **{product['name']}**?",
                color=Config.COLOR_WARNING,
            ),
            view=view, ephemeral=True,
        )
        await view.wait()
        if not view.confirmed:
            return await interaction.edit_original_response(
                embed=info_embed("Dibatalkan", "Tidak jadi dihapus."), view=None
            )

        await self.db.delete_all_product_fields(product_id)
        await interaction.edit_original_response(
            embed=success_embed(
                "Field Dihapus",
                f"Semua required field dari **{product['name']}** berhasil dihapus.",
            ),
            view=None,
        )

    @field_group.command(name="preset", description="Gunakan preset field yang umum dipakai.")
    @app_commands.guild_only()
    @app_commands.describe(
        product_id="ID produk",
        preset="Pilih preset",
    )
    @app_commands.choices(preset=[
        app_commands.Choice(name="Roblox (Username)", value="roblox"),
        app_commands.Choice(name="Mobile Legends (User ID + Zone ID)", value="ml"),
        app_commands.Choice(name="Free Fire (Player ID + Server)", value="ff"),
        app_commands.Choice(name="PUBG Mobile (Player ID)", value="pubg"),
        app_commands.Choice(name="Genshin Impact (UID + Server)", value="genshin"),
        app_commands.Choice(name="Gift Card (Email)", value="giftcard"),
        app_commands.Choice(name="Steam (Steam ID)", value="steam"),
        app_commands.Choice(name="Custom (Isi Manual)", value="custom"),
    ])
    async def field_preset(
        self,
        interaction: discord.Interaction,
        product_id: int,
        preset: str,
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

        # Preset definitions: (field_name, field_label, placeholder, is_required, position)
        presets: dict[str, list[tuple]] = {
            "roblox": [
                ("username_roblox", "Username Roblox", "Contoh: NamaUser123", 1, 1),
            ],
            "ml": [
                ("user_id_ml", "User ID Mobile Legends", "Contoh: 123456789", 1, 1),
                ("zone_id_ml", "Zone ID Mobile Legends", "Contoh: 1234", 1, 2),
            ],
            "ff": [
                ("player_id_ff", "Player ID Free Fire", "Contoh: 123456789", 1, 1),
                ("server_ff", "Server Free Fire", "Contoh: Indonesia", 1, 2),
            ],
            "pubg": [
                ("player_id_pubg", "Player ID PUBG Mobile", "Contoh: 5123456789", 1, 1),
            ],
            "genshin": [
                ("uid_genshin", "UID Genshin Impact", "Contoh: 812345678", 1, 1),
                ("server_genshin", "Server", "Contoh: Asia", 1, 2),
            ],
            "giftcard": [
                ("email", "Email Akun", "Contoh: email@gmail.com", 1, 1),
            ],
            "steam": [
                ("steam_id", "Steam ID / Username Steam", "Contoh: https://steamcommunity.com/id/...", 1, 1),
            ],
            "custom": [],
        }

        if preset == "custom":
            return await interaction.response.send_message(
                embed=info_embed(
                    "Custom Field",
                    f"Gunakan `/field add product_id:{product_id} field_label:Nama Field` untuk menambah field secara manual.",
                ),
                ephemeral=True,
            )

        # Clear existing fields first
        await self.db.delete_all_product_fields(product_id)

        # Add preset fields
        fields_data = presets.get(preset, [])
        for field_name, field_label, placeholder, is_required, position in fields_data:
            await self.db.create_product_field(
                product_id=product_id,
                field_name=field_name,
                field_label=field_label,
                placeholder=placeholder,
                is_required=is_required,
                position=position,
            )

        preset_names = {
            "roblox": "Roblox",
            "ml": "Mobile Legends",
            "ff": "Free Fire",
            "pubg": "PUBG Mobile",
            "genshin": "Genshin Impact",
            "giftcard": "Gift Card",
            "steam": "Steam",
        }

        field_list = "\n".join(
            f"• **{fl}** (`{ph}`)" for _, fl, ph, _, _ in fields_data
        )

        await interaction.response.send_message(
            embed=success_embed(
                f"Preset {preset_names.get(preset, preset)} Diterapkan",
                f"Berhasil menambahkan field ke **{product['name']}**:\n\n{field_list}\n\n"
                f"User akan diminta mengisi data ini saat membeli.",
            ),
            ephemeral=True,
        )
        await self.db.log_activity(
            action="Field Preset Applied",
            actor_id=interaction.user.id,
            actor_name=str(interaction.user),
            target=product["name"],
            details=f"Preset: {preset}",
        )

    @field_group.command(name="preview", description="Preview tampilan form yang akan dilihat user saat beli.")
    @app_commands.guild_only()
    @app_commands.describe(product_id="ID produk")
    async def field_preview(self, interaction: discord.Interaction, product_id: int) -> None:
        await interaction.response.defer(ephemeral=True)

        product = await self.db.get_product(product_id)
        if not product:
            return await interaction.followup.send(
                embed=error_embed("Error", f"Produk ID `{product_id}` tidak ditemukan."),
                ephemeral=True,
            )

        fields = await self.db.get_product_fields(product_id)
        if not fields:
            return await interaction.followup.send(
                embed=info_embed(
                    "Tidak Ada Field",
                    "Produk ini tidak memiliki required field. User langsung ke payment.",
                ),
                ephemeral=True,
            )

        embed = _base_embed(
            title=f"👁️ Preview Form — {product['name']}",
            description=(
                "Ini adalah tampilan form yang akan dilihat user saat membeli produk ini.\n"
                "Modal Discord bisa menampilkan maksimal **5 field**.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=Config.COLOR_INFO,
        )

        for i, f in enumerate(fields[:5], 1):
            required_badge = "🔴 Wajib" if f["is_required"] else "🟡 Opsional"
            embed.add_field(
                name=f"Field {i}: {f['field_label']}",
                value=(
                    f"{required_badge}\n"
                    f"Placeholder: `{f['placeholder'] or 'Tidak ada'}`"
                ),
                inline=False,
            )

        if len(fields) > 5:
            embed.add_field(
                name="⚠️ Perhatian",
                value=f"Produk ini punya {len(fields)} field, tapi Discord hanya bisa tampilkan **5 field** dalam satu modal. Hapus field yang berlebih dengan `/field delete`.",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FieldCog(bot, bot.db))
