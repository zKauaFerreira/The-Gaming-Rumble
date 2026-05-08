from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from services.game_service import GameService
from services.guild_config_service import GuildConfigService
from utils.discord_utils import build_game_embed

LOGGER = logging.getLogger(__name__)


class BuscarGroup(app_commands.Group):
    def __init__(
        self,
        game_service: GameService,
        config_service: GuildConfigService,
    ) -> None:
        super().__init__(
            name="buscar",
            description="[ ⚡USER ] Comandos de busca no catálogo.",
        )
        self.game_service = game_service
        self.config_service = config_service

    def _get_ui_emoji(
        self,
        interaction: discord.Interaction,
        key: str,
    ) -> discord.Emoji | discord.PartialEmoji | str | None:
        guild = interaction.guild
        if guild is None:
            return None

        emoji_value = self.config_service.get_ui_emoji(guild.id, key)
        if emoji_value is None:
            return None

        if emoji_value.startswith("id:"):
            try:
                emoji_id = int(emoji_value.split(":", 1)[1])
            except ValueError:
                return None
            return guild.get_emoji(emoji_id) or self.bot.get_emoji(emoji_id)  # type: ignore[attr-defined]

        return emoji_value

    async def _autocomplete_jogo(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is not None and not self.config_service.can_search(
            interaction.guild,
            interaction.user,
        ):
            return []

        titles = self.game_service.autocomplete_titles(current, limit=25)
        return [
            app_commands.Choice(name=title[:100], value=title)
            for title in titles
        ]

    @app_commands.command(
        name="jogo",
        description="[ ⚡USER ] Busca um jogo no catálogo principal.",
    )
    @app_commands.describe(nome="Nome completo ou parcial do jogo")
    @app_commands.autocomplete(nome=_autocomplete_jogo)
    async def jogo(
        self,
        interaction: discord.Interaction,
        nome: str,
    ) -> None:
        if interaction.guild is not None and not self.config_service.can_search(
            interaction.guild,
            interaction.user,
        ):
            await interaction.response.send_message(
                "Você não tem permissão para buscar jogos neste servidor.",
                ephemeral=True,
            )
            return

        LOGGER.info(
            "Slash search requested by user=%s guild=%s query=%r",
            interaction.user.id,
            interaction.guild.id if interaction.guild else None,
            nome,
        )
        result = self.game_service.best_match(nome)
        if result is None:
            LOGGER.info(
                "Slash search had no result for user=%s query=%r",
                interaction.user.id,
                nome,
            )
            await interaction.response.send_message(
                "Não encontrei um jogo parecido com essa busca.",
                ephemeral=True,
            )
            return

        LOGGER.info(
            "Slash search matched user=%s query=%r game=%r score=%.2f",
            interaction.user.id,
            nome,
            result.game.title,
            result.score,
        )
        download_app_emoji = self._get_ui_emoji(interaction, "download_app_button")
        requirements_button_emoji = self._get_ui_emoji(interaction, "requirements_button")
        clear_active = getattr(interaction.client, "clear_active_game_ephemeral", None)
        if callable(clear_active):
            await clear_active(
                guild_id=interaction.guild.id if interaction.guild else None,
                user_id=interaction.user.id,
            )
        embed, view = build_game_embed(
            result,
            download_app_emoji=download_app_emoji,
            requirements_button_emoji=requirements_button_emoji,
            requester_id=interaction.user.id,
            guild=interaction.guild,
            config_service=self.config_service,
            share_enabled=(
                self.config_service.can_share_game(interaction.guild, interaction.user)
                if interaction.guild is not None
                else False
            ),
        )
        await interaction.response.send_message(
            content=interaction.user.mention,
            embed=embed,
            view=view,
            ephemeral=True,
        )
        register_active = getattr(interaction.client, "register_active_game_ephemeral", None)
        if callable(register_active):
            register_active(
                guild_id=interaction.guild.id if interaction.guild else None,
                user_id=interaction.user.id,
                delete_callback=interaction.delete_original_response,
            )


class GamesCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        game_service: GameService,
        config_service: GuildConfigService,
    ) -> None:
        self.bot = bot
        self.game_service = game_service
        self.config_service = config_service
        self.buscar_group = BuscarGroup(game_service, config_service)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.buscar_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.buscar_group.name, type=self.buscar_group.type)


async def setup(bot: commands.Bot) -> None:
    game_service: GameService = bot.game_service  # type: ignore[attr-defined]
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    await bot.add_cog(GamesCog(bot, game_service, config_service))
