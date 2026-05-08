from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from services.guild_config_service import GuildConfigService
from utils.discord_utils import build_bot_settings_embed

LOGGER = logging.getLogger(__name__)
TIMEOUT_OPTIONS = [0, 3, 5, 10, 15, 30, 45, 60, 90, 120]


class TimeoutSelect(discord.ui.Select):
    def __init__(self, view_ref: "BotSettingsView") -> None:
        current_timeout = view_ref.config_service.get_delete_notice_after_seconds(
            view_ref.guild.id
        )
        options = [
            discord.SelectOption(
                label=f"{seconds} segundo(s)",
                value=str(seconds),
                default=(seconds == current_timeout),
            )
            for seconds in TIMEOUT_OPTIONS
        ]
        super().__init__(
            placeholder="Selecione o tempo para apagar o aviso",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.view_ref.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        seconds = int(self.values[0])
        self.view_ref.config_service.set_delete_notice_after_seconds(
            self.view_ref.guild.id,
            seconds,
        )
        LOGGER.info(
            "Delete notice timeout configured guild=%s user=%s seconds=%s",
            self.view_ref.guild.id,
            interaction.user.id,
            seconds,
        )
        await interaction.response.edit_message(
            embed=build_bot_settings_embed(
                self.view_ref.guild,
                self.view_ref.config_service.get_delete_notice_after_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_ephemeral_game_result_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_panel_role_id(self.view_ref.guild.id),
                self.view_ref.config_service.get_share_role_id(self.view_ref.guild.id),
            ),
            view=BotSettingsView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
            ),
        )


class ExactMatchTimeoutSelect(discord.ui.Select):
    def __init__(self, view_ref: "BotSettingsView") -> None:
        current_timeout = view_ref.config_service.get_ephemeral_game_result_seconds(
            view_ref.guild.id
        )
        options = [
            discord.SelectOption(
                label=f"{seconds} segundo(s)",
                value=str(seconds),
                default=(seconds == current_timeout),
            )
            for seconds in TIMEOUT_OPTIONS
            if seconds > 0
        ]
        super().__init__(
            placeholder="Selecione o tempo da confirmação exata",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.view_ref.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        seconds = int(self.values[0])
        self.view_ref.config_service.set_ephemeral_game_result_seconds(
            self.view_ref.guild.id,
            seconds,
        )
        LOGGER.info(
            "Exact-match confirmation timeout configured guild=%s user=%s seconds=%s",
            self.view_ref.guild.id,
            interaction.user.id,
            seconds,
        )
        await interaction.response.edit_message(
            embed=build_bot_settings_embed(
                self.view_ref.guild,
                self.view_ref.config_service.get_delete_notice_after_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_ephemeral_game_result_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_panel_role_id(self.view_ref.guild.id),
                self.view_ref.config_service.get_share_role_id(self.view_ref.guild.id),
            ),
            view=BotSettingsView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
            ),
        )


class PanelRoleSelect(discord.ui.RoleSelect):
    def __init__(self, view_ref: "BotSettingsView") -> None:
        super().__init__(
            placeholder="Selecione o cargo para marcar acima da embed",
            min_values=1,
            max_values=1,
            row=2,
        )
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.view_ref.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        selected_role = self.values[0]
        self.view_ref.config_service.set_panel_role_id(
            self.view_ref.guild.id,
            selected_role.id,
        )
        LOGGER.info(
            "Panel role configured guild=%s user=%s role=%s",
            self.view_ref.guild.id,
            interaction.user.id,
            selected_role.id,
        )
        await interaction.response.edit_message(
            embed=build_bot_settings_embed(
                self.view_ref.guild,
                self.view_ref.config_service.get_delete_notice_after_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_ephemeral_game_result_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_panel_role_id(self.view_ref.guild.id),
                self.view_ref.config_service.get_share_role_id(self.view_ref.guild.id),
            ),
            view=BotSettingsView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
            ),
        )


class ShareRoleSelect(discord.ui.RoleSelect):
    def __init__(self, view_ref: "BotSettingsView") -> None:
        super().__init__(
            placeholder="Selecione o cargo permitido para compartilhar",
            min_values=1,
            max_values=1,
            row=3,
        )
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.view_ref.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        selected_role = self.values[0]
        self.view_ref.config_service.set_share_role_id(
            self.view_ref.guild.id,
            selected_role.id,
        )
        LOGGER.info(
            "Share role configured guild=%s user=%s role=%s",
            self.view_ref.guild.id,
            interaction.user.id,
            selected_role.id,
        )
        await interaction.response.edit_message(
            embed=build_bot_settings_embed(
                self.view_ref.guild,
                self.view_ref.config_service.get_delete_notice_after_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_ephemeral_game_result_seconds(
                    self.view_ref.guild.id
                ),
                self.view_ref.config_service.get_panel_role_id(self.view_ref.guild.id),
                self.view_ref.config_service.get_share_role_id(self.view_ref.guild.id),
            ),
            view=BotSettingsView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
            ),
        )


class BotSettingsView(discord.ui.View):
    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        guild: discord.Guild,
        requester_id: int,
    ) -> None:
        super().__init__(timeout=300)
        self.config_service = config_service
        self.guild = guild
        self.requester_id = requester_id
        self.add_item(TimeoutSelect(self))
        self.add_item(ExactMatchTimeoutSelect(self))
        self.add_item(PanelRoleSelect(self))
        self.add_item(ShareRoleSelect(self))
        self.clear_panel_role.disabled = self.config_service.get_panel_role_id(guild.id) is None
        self.clear_share_role.disabled = self.config_service.get_share_role_id(guild.id) is None

    @discord.ui.button(label="Limpar cargo do painel", style=discord.ButtonStyle.danger, row=4)
    async def clear_panel_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        self.config_service.set_panel_role_id(self.guild.id, None)
        LOGGER.info(
            "Panel role cleared guild=%s user=%s",
            self.guild.id,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=build_bot_settings_embed(
                self.guild,
                self.config_service.get_delete_notice_after_seconds(self.guild.id),
                self.config_service.get_ephemeral_game_result_seconds(self.guild.id),
                self.config_service.get_panel_role_id(self.guild.id),
                self.config_service.get_share_role_id(self.guild.id),
            ),
            view=BotSettingsView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )

    @discord.ui.button(label="Limpar cargo de permissão do compartilhar", style=discord.ButtonStyle.danger, row=4)
    async def clear_share_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        self.config_service.set_share_role_id(self.guild.id, None)
        LOGGER.info(
            "Share role cleared guild=%s user=%s",
            self.guild.id,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=build_bot_settings_embed(
                self.guild,
                self.config_service.get_delete_notice_after_seconds(self.guild.id),
                self.config_service.get_ephemeral_game_result_seconds(self.guild.id),
                self.config_service.get_panel_role_id(self.guild.id),
                self.config_service.get_share_role_id(self.guild.id),
            ),
            view=BotSettingsView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )


class BotGroup(app_commands.Group):
    def __init__(self, config_service: GuildConfigService) -> None:
        super().__init__(
            name="bot",
            description="[ 🔐ADMIN ] Configurações gerais do bot.",
        )
        self.config_service = config_service

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Esse comando só pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return False

        if self.config_service.can_manage(interaction.guild, interaction.user):
            return True

        await interaction.response.send_message(
            "Você não tem permissão para usar os comandos administrativos do bot.",
            ephemeral=True,
        )
        return False

    @app_commands.command(
        name="config",
        description="[ 🔐ADMIN ] Abre o painel de configurações gerais do bot.",
    )
    async def config(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        await interaction.response.send_message(
            embed=build_bot_settings_embed(
                guild,
                self.config_service.get_delete_notice_after_seconds(guild.id),
                self.config_service.get_ephemeral_game_result_seconds(guild.id),
                self.config_service.get_panel_role_id(guild.id),
                self.config_service.get_share_role_id(guild.id),
            ),
            view=BotSettingsView(
                config_service=self.config_service,
                guild=guild,
                requester_id=interaction.user.id,
            ),
            ephemeral=True,
        )


class BotConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config_service: GuildConfigService) -> None:
        self.bot = bot
        self.config_service = config_service
        self.bot_group = BotGroup(config_service)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.bot_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.bot_group.name, type=self.bot_group.type)


async def setup(bot: commands.Bot) -> None:
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    await bot.add_cog(BotConfigCog(bot, config_service))
