from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from services.guild_config_service import GuildConfigService

LOGGER = logging.getLogger(__name__)


class SystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config_service: GuildConfigService) -> None:
        self.bot = bot
        self.config_service = config_service

    @app_commands.command(
        name="ping",
        description="[ 🔐ADMIN ] Verifica se o bot está online.",
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        if interaction.guild is not None and not self.config_service.can_manage(
            interaction.guild,
            interaction.user,
        ):
            await interaction.response.send_message(
                "Você não tem permissão para usar os comandos administrativos do bot.",
                ephemeral=True,
            )
            return

        latency_ms = round(self.bot.latency * 1000)
        LOGGER.info(
            "Ping command used by user=%s guild=%s latency_ms=%s",
            interaction.user.id,
            interaction.guild.id if interaction.guild else None,
            latency_ms,
        )
        await interaction.response.send_message(
            f"Pong. Latência atual: {latency_ms} ms",
            ephemeral=True,
        )

    @app_commands.command(
        name="clear",
        description="[ 🔐ADMIN ] Limpa o canal configurado do bot, preservando a mensagem principal.",
    )
    async def clear(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Esse comando só pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        if not self.config_service.can_manage(interaction.guild, interaction.user):
            await interaction.response.send_message(
                "Você não tem permissão para usar os comandos administrativos do bot.",
                ephemeral=True,
            )
            return

        channel_id = self.config_service.get_bot_channel_id(interaction.guild.id)
        if channel_id is None:
            await interaction.response.send_message(
                "Nenhum canal do bot foi configurado ainda.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "O canal configurado não está acessível no momento.",
                ephemeral=True,
            )
            return

        welcome_message_id = self.config_service.get_welcome_message_id(interaction.guild.id)
        deleted_messages = 0

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            async for message in channel.history(limit=None):
                if welcome_message_id is not None and message.id == welcome_message_id:
                    continue
                try:
                    await message.delete()
                    deleted_messages += 1
                except (discord.NotFound, discord.Forbidden):
                    continue
                except discord.HTTPException as exc:
                    LOGGER.warning(
                        "Failed to delete message during /clear guild=%s channel=%s message=%s error=%s",
                        interaction.guild.id,
                        channel.id,
                        message.id,
                        exc,
                    )
        except discord.HTTPException as exc:
            LOGGER.warning(
                "Failed to inspect channel during /clear guild=%s channel=%s error=%s",
                interaction.guild.id,
                channel.id,
                exc,
            )
            await interaction.followup.send(
                "Não consegui limpar o canal do bot agora.",
                ephemeral=True,
            )
            return

        LOGGER.info(
            "Clear command used guild=%s channel=%s user=%s deleted_messages=%s",
            interaction.guild.id,
            channel.id,
            interaction.user.id,
            deleted_messages,
        )
        await interaction.followup.send(
            f"Canal do bot limpo com sucesso. Mensagens removidas: {deleted_messages}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    await bot.add_cog(SystemCog(bot, config_service))
