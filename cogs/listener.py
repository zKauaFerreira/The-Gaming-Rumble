from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from domain.models import SearchResult
from services.game_service import GameService
from services.guild_config_service import GuildConfigService
from utils.discord_utils import (
    build_exact_match_confirmation_embed,
    build_game_embed,
    build_timed_selection_embed,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class ActivePromptState:
    message: discord.Message
    delete_task: asyncio.Task[None]


async def send_ephemeral_game_result(
    interaction: discord.Interaction,
    result: SearchResult,
    *,
    download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None,
    requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
    config_service: GuildConfigService,
) -> None:
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
        config_service=config_service,
        share_enabled=(
            config_service.can_share_game(interaction.guild, interaction.user)
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
    LOGGER.info(
        "Ephemeral game result sent user=%s game=%r",
        interaction.user.id,
        result.game.title,
    )
    register_active = getattr(interaction.client, "register_active_game_ephemeral", None)
    if callable(register_active):
        register_active(
            guild_id=interaction.guild.id if interaction.guild else None,
            user_id=interaction.user.id,
            delete_callback=interaction.delete_original_response,
        )


class GameSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        results: list[SearchResult],
        requester_id: int,
        original_query: str,
        download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        config_service: GuildConfigService,
    ) -> None:
        self.results = results
        self.requester_id = requester_id
        self.original_query = original_query
        self.download_app_emoji = download_app_emoji
        self.requirements_button_emoji = requirements_button_emoji
        self.config_service = config_service
        options = [
            discord.SelectOption(
                label=result.game.title[:100],
                description=(result.game.file_size or "Tamanho N/A")[:100],
                value=str(index),
            )
            for index, result in enumerate(results)
        ]
        super().__init__(
            placeholder="Selecione o jogo correto",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            LOGGER.info(
                "Selection denied clicker=%s owner=%s query=%r",
                interaction.user.id,
                self.requester_id,
                self.original_query,
            )
            await interaction.response.send_message(
                "Só quem fez a busca pode escolher esse resultado.",
                ephemeral=True,
            )
            return

        selected_result = self.results[int(self.values[0])]
        LOGGER.info(
            "Selection accepted user=%s query=%r game=%r score=%.2f",
            interaction.user.id,
            self.original_query,
            selected_result.game.title,
            selected_result.score,
        )
        await send_ephemeral_game_result(
            interaction,
            selected_result,
            download_app_emoji=self.download_app_emoji,
            requirements_button_emoji=self.requirements_button_emoji,
            config_service=self.config_service,
        )

        if interaction.message is not None:
            await interaction.message.delete()

        if self.view is not None:
            self.view.stop()


class CancelSelectionButton(discord.ui.Button["GameSelectionView"]):
    def __init__(self, *, requester_id: int) -> None:
        super().__init__(
            label="Cancelar",
            style=discord.ButtonStyle.secondary,
            emoji="❌",
            row=1,
        )
        self.requester_id = requester_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem fez a busca pode cancelar essa seleção.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if interaction.message is not None:
            try:
                await interaction.message.delete()
            except (discord.Forbidden, discord.NotFound):
                return
            except discord.HTTPException as exc:
                LOGGER.warning(
                    "Failed to delete selection message %s: %s",
                    interaction.message.id,
                    exc,
                )
        if self.view is not None:
            self.view.stop()


class GameSelectionView(discord.ui.View):
    def __init__(
        self,
        *,
        results: list[SearchResult],
        requester_id: int,
        original_query: str,
        download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        config_service: GuildConfigService,
        timeout_seconds: int,
    ) -> None:
        super().__init__(timeout=timeout_seconds)
        self.add_item(
            GameSelect(
                results=results,
                requester_id=requester_id,
                original_query=original_query,
                download_app_emoji=download_app_emoji,
                requirements_button_emoji=requirements_button_emoji,
                config_service=config_service,
            )
        )
        self.add_item(CancelSelectionButton(requester_id=requester_id))


class ExactMatchConfirmationView(discord.ui.View):
    def __init__(
        self,
        *,
        result: SearchResult,
        requester_id: int,
        download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        config_service: GuildConfigService,
        confirm_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        decline_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        timeout_seconds: int,
    ) -> None:
        super().__init__(timeout=timeout_seconds)
        self.result = result
        self.requester_id = requester_id
        self.download_app_emoji = download_app_emoji
        self.requirements_button_emoji = requirements_button_emoji
        self.config_service = config_service
        self.timeout_seconds = timeout_seconds
        self.confirm_game.emoji = confirm_emoji or "✅"
        self.decline_game.emoji = decline_emoji or "❌"

    async def _delete_public_message(self, interaction: discord.Interaction) -> None:
        if interaction.message is None:
            return
        try:
            await interaction.message.delete()
        except (discord.Forbidden, discord.NotFound):
            return
        except discord.HTTPException as exc:
            LOGGER.warning(
                "Failed to delete confirmation message %s: %s",
                interaction.message.id,
                exc,
            )

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirm_game(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem fez a busca pode confirmar esse resultado.",
                ephemeral=True,
            )
            return

        await send_ephemeral_game_result(
            interaction,
            self.result,
            download_app_emoji=self.download_app_emoji,
            requirements_button_emoji=self.requirements_button_emoji,
            config_service=self.config_service,
        )
        await self._delete_public_message(interaction)
        self.stop()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.secondary)
    async def decline_game(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem fez a busca pode recusar esse resultado.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        await self._delete_public_message(interaction)
        self.stop()


class ListenerCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        game_service: GameService,
        config_service: GuildConfigService,
    ) -> None:
        self.bot = bot
        self.game_service = game_service
        self.config_service = config_service
        self._active_prompts: dict[tuple[int, int], ActivePromptState] = {}

    def _prompt_key(self, guild_id: int, user_id: int) -> tuple[int, int]:
        return (guild_id, user_id)

    def _clear_prompt_state_if_matches(
        self,
        *,
        guild_id: int,
        user_id: int,
        message_id: int,
    ) -> None:
        key = self._prompt_key(guild_id, user_id)
        state = self._active_prompts.get(key)
        if state is not None and state.message.id == message_id:
            self._active_prompts.pop(key, None)

    async def _schedule_prompt_expiration(
        self,
        *,
        guild_id: int,
        user_id: int,
        message: discord.Message,
        delay: int,
    ) -> None:
        try:
            await asyncio.sleep(delay)
            await self._delete_message_safely(message)
        finally:
            self._clear_prompt_state_if_matches(
                guild_id=guild_id,
                user_id=user_id,
                message_id=message.id,
            )

    async def _upsert_prompt_message(
        self,
        *,
        owner: discord.Member,
        channel: discord.TextChannel,
        embed: discord.Embed,
        view: discord.ui.View,
        timeout_seconds: int,
    ) -> discord.Message:
        guild = channel.guild
        key = self._prompt_key(guild.id, owner.id)
        existing_state = self._active_prompts.get(key)

        if existing_state is not None:
            existing_state.delete_task.cancel()
            try:
                await existing_state.message.edit(embed=embed, view=view)
                message = existing_state.message
                LOGGER.info(
                    "Prompt message updated guild=%s user=%s message=%s timeout=%s",
                    guild.id,
                    owner.id,
                    message.id,
                    timeout_seconds,
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                LOGGER.warning(
                    "Failed to update prompt message guild=%s user=%s message=%s error=%s",
                    guild.id,
                    owner.id,
                    existing_state.message.id,
                    exc,
                )
                message = await channel.send(embed=embed, view=view)
            delete_task = self.bot.loop.create_task(
                self._schedule_prompt_expiration(
                    guild_id=guild.id,
                    user_id=owner.id,
                    message=message,
                    delay=timeout_seconds,
                )
            )
            self._active_prompts[key] = ActivePromptState(message=message, delete_task=delete_task)
            return message

        message = await channel.send(embed=embed, view=view)
        delete_task = self.bot.loop.create_task(
            self._schedule_prompt_expiration(
                guild_id=guild.id,
                user_id=owner.id,
                message=message,
                delay=timeout_seconds,
            )
        )
        self._active_prompts[key] = ActivePromptState(message=message, delete_task=delete_task)
        LOGGER.info(
            "Prompt message created guild=%s user=%s message=%s timeout=%s",
            guild.id,
            owner.id,
            message.id,
            timeout_seconds,
        )
        return message

    def _get_ui_emoji(self, guild: discord.Guild, key: str, fallback: str) -> str:
        emoji_value = self.config_service.get_ui_emoji(guild.id, key)
        if emoji_value is None:
            return fallback

        if emoji_value.startswith("id:"):
            try:
                emoji_id = int(emoji_value.split(":", 1)[1])
            except ValueError:
                return fallback
            emoji = guild.get_emoji(emoji_id) or self.bot.get_emoji(emoji_id)
            return str(emoji) if emoji is not None else fallback

        return emoji_value

    async def _delete_message_safely(
        self,
        message: discord.Message,
        delay: float = 0,
    ) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            return
        except discord.HTTPException as exc:
            LOGGER.warning("Falha ao apagar mensagem %s: %s", message.id, exc)

    async def _send_temporary_notice(
        self,
        message: discord.Message,
        content: str,
    ) -> None:
        delete_after_seconds = self.config_service.get_delete_notice_after_seconds(
            message.guild.id
        )
        info_emoji = self._get_ui_emoji(message.guild, "info", "ℹ️")

        await self._delete_message_safely(message)
        LOGGER.info(
            "Mensagem do usuário apagada por falta de permissão user=%s channel=%s",
            message.author.id,
            message.channel.id,
        )

        bot_message = await message.channel.send(
            f"{info_emoji} {message.author.mention} {content}"
        )
        LOGGER.info(
            "Aviso temporário enviado user=%s channel=%s delete_after=%s",
            message.author.id,
            message.channel.id,
            delete_after_seconds,
        )
        self.bot.loop.create_task(
            self._delete_message_safely(bot_message, delay=delete_after_seconds)
        )

    async def _send_exact_match_confirmation(
        self,
        message: discord.Message,
        result: SearchResult,
        *,
        download_app_emoji: str,
        requirements_button_emoji: str,
        confirm_emoji: str,
        decline_emoji: str,
    ) -> None:
        timeout_seconds = self.config_service.get_ephemeral_game_result_seconds(
            message.guild.id
        )
        expires_at_timestamp = int(time.time()) + timeout_seconds
        confirmation_embed = build_exact_match_confirmation_embed(
            result,
            expires_at_timestamp=expires_at_timestamp,
        )
        confirmation_view = ExactMatchConfirmationView(
            result=result,
            requester_id=message.author.id,
            download_app_emoji=download_app_emoji,
            requirements_button_emoji=requirements_button_emoji,
            config_service=self.config_service,
            confirm_emoji=confirm_emoji,
            decline_emoji=decline_emoji,
            timeout_seconds=timeout_seconds,
        )
        confirmation_message = await self._upsert_prompt_message(
            owner=message.author,
            channel=message.channel,
            embed=confirmation_embed,
            view=confirmation_view,
            timeout_seconds=timeout_seconds,
        )
        LOGGER.info(
            "Exact-match confirmation sent user=%s game=%r expires_in=%s expires_at=%s message=%s",
            message.author.id,
            result.game.title,
            timeout_seconds,
            expires_at_timestamp,
            confirmation_message.id,
        )

    async def _send_timed_selection(
        self,
        message: discord.Message,
        query: str,
        results: list[SearchResult],
        *,
        download_app_emoji: str,
        requirements_button_emoji: str,
    ) -> None:
        timeout_seconds = self.config_service.get_ephemeral_game_result_seconds(
            message.guild.id
        )
        expires_at_timestamp = int(time.time()) + timeout_seconds
        selection_embed = build_timed_selection_embed(
            query,
            results,
            expires_at_timestamp=expires_at_timestamp,
        )
        selection_view = GameSelectionView(
            results=results,
            requester_id=message.author.id,
            original_query=query,
            download_app_emoji=download_app_emoji,
            requirements_button_emoji=requirements_button_emoji,
            config_service=self.config_service,
            timeout_seconds=timeout_seconds,
        )
        selection_message = await self._upsert_prompt_message(
            owner=message.author,
            channel=message.channel,
            embed=selection_embed,
            view=selection_view,
            timeout_seconds=timeout_seconds,
        )
        LOGGER.info(
            "Timed selection sent user=%s query=%r expires_in=%s expires_at=%s message=%s",
            message.author.id,
            query,
            timeout_seconds,
            expires_at_timestamp,
            selection_message.id,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        configured_channel_id = self.config_service.get_bot_channel_id(message.guild.id)
        if configured_channel_id is None or message.channel.id != configured_channel_id:
            return

        content = message.content.strip()
        if not content:
            return

        if not self.config_service.can_search(message.guild, message.author):
            LOGGER.info(
                "Channel search denied user=%s guild=%s channel=%s query=%r",
                message.author.id,
                message.guild.id,
                message.channel.id,
                content,
            )
            await self._send_temporary_notice(
                message,
                "Você não tem permissão para buscar jogos neste servidor.",
            )
            return

        LOGGER.info(
            "Channel search message user=%s guild=%s channel=%s query=%r",
            message.author.id,
            message.guild.id,
            message.channel.id,
            content,
        )
        results = self.game_service.search_games(content, limit=5)
        if not results:
            LOGGER.info(
                "Channel search had no result user=%s query=%r",
                message.author.id,
                content,
            )
            await message.reply("Não encontrei um jogo parecido com essa busca.")
            return

        LOGGER.info(
            "Channel search matched user=%s query=%r candidates=%s top_game=%r top_score=%.2f",
            message.author.id,
            content,
            len(results),
            results[0].game.title,
            results[0].score,
        )
        try:
            await message.delete()
            LOGGER.info(
                "User search message deleted user=%s channel=%s",
                message.author.id,
                message.channel.id,
            )
        except discord.Forbidden:
            LOGGER.warning(
                "Missing permission to delete user message user=%s channel=%s",
                message.author.id,
                message.channel.id,
            )
        except discord.HTTPException as exc:
            LOGGER.warning(
                "Failed to delete user message user=%s channel=%s error=%s",
                message.author.id,
                message.channel.id,
                exc,
            )

        top_result = results[0]
        download_app_emoji = self._get_ui_emoji(
            message.guild,
            "download_app_button",
            "🎮",
        )
        requirements_button_emoji = self._get_ui_emoji(
            message.guild,
            "requirements_button",
            "📋",
        )
        confirm_emoji = self._get_ui_emoji(message.guild, "confirm_button", "✅")
        decline_emoji = self._get_ui_emoji(message.guild, "decline_button", "❌")

        if top_result.score >= 1.0:
            LOGGER.info(
                "Channel search exact match user=%s query=%r game=%r",
                message.author.id,
                content,
                top_result.game.title,
            )
            await self._send_exact_match_confirmation(
                message,
                top_result,
                download_app_emoji=download_app_emoji,
                requirements_button_emoji=requirements_button_emoji,
                confirm_emoji=confirm_emoji,
                decline_emoji=decline_emoji,
            )
            return

        selection_results = [result for result in results if result.score < 1.0]
        if not selection_results:
            selection_results = results[:1]

        await self._send_timed_selection(
            message,
            content,
            selection_results,
            download_app_emoji=download_app_emoji,
            requirements_button_emoji=requirements_button_emoji,
        )


async def setup(bot: commands.Bot) -> None:
    game_service: GameService = bot.game_service  # type: ignore[attr-defined]
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    await bot.add_cog(ListenerCog(bot, game_service, config_service))
