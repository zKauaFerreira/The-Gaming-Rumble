from __future__ import annotations

import logging
import math

import discord
from discord import app_commands
from discord.ext import commands

from services.guild_config_service import GuildConfigService
from services.game_service import GameService
from services.stats_service import StatsService
from utils.discord_utils import (
    CLIENT_RELEASES_URL,
    build_game_embed,
    build_recent_games_text,
    build_welcome_embed,
    build_welcome_logo_file,
)

LOGGER = logging.getLogger(__name__)
CATALOG_PAGE_SIZE = 3


def _build_catalog_page_embeds(
    games: list,
    *,
    page_index: int,
    page_size: int = CATALOG_PAGE_SIZE,
) -> list[discord.Embed]:
    total_games = len(games)
    total_pages = max(math.ceil(total_games / page_size), 1)
    clamped_page = max(0, min(page_index, total_pages - 1))
    start = clamped_page * page_size
    end = min(start + page_size, total_games)
    page_games = games[start:end]

    embeds: list[discord.Embed] = []
    for game in page_games:
        embed = discord.Embed(
            title=game.title,
            url=game.url,
            description=(game.description or "Sem descrição adicional no catálogo.")[:300],
            color=discord.Color.blue(),
        )
        if game.cover_url:
            embed.set_image(url=game.cover_url)
        embed.set_footer(
            text=(
                f"Catálogo • Página {clamped_page + 1}/{total_pages} • "
                f"Mostrando {start + 1}-{end} de {total_games}"
            )
        )
        embeds.append(embed)

    return embeds


class CatalogPreviousButton(discord.ui.Button["CatalogPaginationView"]):
    def __init__(self) -> None:
        super().__init__(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.change_page(interaction, self.view.page_index - 1)


class CatalogPageIndicatorButton(discord.ui.Button["CatalogPaginationView"]):
    def __init__(self, label: str) -> None:
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await interaction.response.send_modal(
            CatalogJumpModal(
                requester_id=self.view.requester_id,
                total_pages=self.view.total_pages,
                current_page=self.view.page_index + 1,
                parent_view=self.view,
            )
        )


class CatalogNextButton(discord.ui.Button["CatalogPaginationView"]):
    def __init__(self) -> None:
        super().__init__(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.change_page(interaction, self.view.page_index + 1)


class CatalogJumpModal(discord.ui.Modal, title="Ir para página"):
    page_input = discord.ui.TextInput(
        label="Página",
        placeholder="Digite o número da página",
        required=True,
        max_length=8,
    )

    def __init__(
        self,
        *,
        requester_id: int,
        total_pages: int,
        current_page: int,
        parent_view: "CatalogPaginationView",
    ) -> None:
        super().__init__()
        self.requester_id = requester_id
        self.total_pages = total_pages
        self.current_page = current_page
        self.parent_view = parent_view
        self.page_input.default = str(current_page)
        self.page_input.placeholder = f"Máximo: {total_pages}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu o catálogo pode navegar por ele.",
                ephemeral=True,
            )
            return

        raw_page = self.page_input.value.strip()
        if not raw_page.isdigit():
            await interaction.response.send_message(
                f"Informe um número de página válido. Máximo: {self.total_pages}.",
                ephemeral=True,
            )
            return

        target_page = int(raw_page)
        if target_page < 1 or target_page > self.total_pages:
            await interaction.response.send_message(
                f"Página fora do intervalo. Máximo: {self.total_pages}.",
                ephemeral=True,
            )
            return

        await self.parent_view.change_page(interaction, target_page - 1)


class CatalogPaginationView(discord.ui.View):
    def __init__(
        self,
        *,
        requester_id: int,
        games: list,
        page_index: int = 0,
        page_size: int = CATALOG_PAGE_SIZE,
    ) -> None:
        super().__init__(timeout=300)
        self.requester_id = requester_id
        self.games = games
        self.page_index = page_index
        self.page_size = page_size
        self.total_pages = max(math.ceil(len(games) / page_size), 1)

        previous_button = CatalogPreviousButton()
        previous_button.disabled = self.page_index <= 0
        self.add_item(previous_button)
        self.add_item(
            CatalogPageIndicatorButton(
                label=f"{self.page_index + 1}/{self.total_pages}"
            )
        )
        next_button = CatalogNextButton()
        next_button.disabled = self.page_index >= self.total_pages - 1
        self.add_item(next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "Só quem abriu o catálogo pode navegar por ele.",
            ephemeral=True,
        )
        return False

    async def change_page(
        self,
        interaction: discord.Interaction,
        page_index: int,
    ) -> None:
        new_page = max(0, min(page_index, self.total_pages - 1))
        await interaction.response.edit_message(
            embeds=_build_catalog_page_embeds(
                self.games,
                page_index=new_page,
                page_size=self.page_size,
            ),
            view=CatalogPaginationView(
                requester_id=self.requester_id,
                games=self.games,
                page_index=new_page,
                page_size=self.page_size,
            ),
        )


class CatalogButton(discord.ui.Button):
    CUSTOM_ID = "welcome_panel:catalog"

    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        game_service: GameService,
        guild: discord.Guild | None,
        emoji: discord.Emoji | discord.PartialEmoji | str,
    ) -> None:
        super().__init__(
            label="Catálogo",
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=self.CUSTOM_ID,
        )
        self.config_service = config_service
        self.game_service = game_service
        self.guild = guild

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = self.guild or interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Esse botão só pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        if not self.config_service.can_search(guild, interaction.user):
            await interaction.response.send_message(
                "Você não tem permissão para buscar jogos neste servidor.",
                ephemeral=True,
            )
            return

        games = self.game_service.catalog_games()
        if not games:
            await interaction.response.send_message(
                "Não encontrei jogos com banner disponíveis no catálogo.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embeds=_build_catalog_page_embeds(games, page_index=0),
            view=CatalogPaginationView(
                requester_id=interaction.user.id,
                games=games,
                page_index=0,
            ),
            ephemeral=True,
        )


class WelcomePanelView(discord.ui.View):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        config_service: GuildConfigService,
        game_service: GameService,
        guild: discord.Guild,
        download_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        catalog_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        surprise_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.config_service = config_service
        self.game_service = game_service
        self.guild = guild
        self.add_item(
            discord.ui.Button(
                label="Baixar Client",
                emoji=download_button_emoji or "🎮",
                style=discord.ButtonStyle.link,
                url=CLIENT_RELEASES_URL,
            )
        )
        self.add_item(
            CatalogButton(
                config_service=config_service,
                game_service=game_service,
                guild=guild,
                emoji=catalog_button_emoji or "📚",
            )
        )
        self.add_item(
            SurpriseMeButton(
                config_service=config_service,
                game_service=game_service,
                guild=guild,
                emoji=surprise_button_emoji or "🎲",
            )
        )


class SurpriseMeButton(discord.ui.Button):
    CUSTOM_ID = "welcome_panel:surprise_me"

    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        game_service: GameService,
        guild: discord.Guild | None,
        emoji: discord.Emoji | discord.PartialEmoji | str,
    ) -> None:
        super().__init__(
            label="Surpreenda-me",
            emoji=emoji,
            style=discord.ButtonStyle.primary,
            custom_id=self.CUSTOM_ID,
        )
        self.config_service = config_service
        self.game_service = game_service
        self.guild = guild

    def _get_ui_emoji(
        self,
        guild: discord.Guild,
        key: str,
        interaction: discord.Interaction,
    ) -> discord.Emoji | discord.PartialEmoji | str | None:
        emoji_value = self.config_service.get_ui_emoji(guild.id, key)
        if emoji_value is None:
            return None

        if emoji_value.startswith("id:"):
            try:
                emoji_id = int(emoji_value.split(":", 1)[1])
            except ValueError:
                return None
            return guild.get_emoji(emoji_id) or interaction.client.get_emoji(emoji_id)

        return emoji_value

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = self.guild or interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Esse botão só pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        if not self.config_service.can_search(guild, interaction.user):
            await interaction.response.send_message(
                "Você não tem permissão para buscar jogos neste servidor.",
                ephemeral=True,
            )
            return

        result = self.game_service.random_game()
        if result is None:
            await interaction.response.send_message(
                "Não encontrei jogos disponíveis no catálogo.",
                ephemeral=True,
            )
            return

        download_app_emoji = self._get_ui_emoji(
            guild,
            "download_app_button",
            interaction,
        )
        requirements_button_emoji = self._get_ui_emoji(
            guild,
            "requirements_button",
            interaction,
        )
        clear_active = getattr(interaction.client, "clear_active_game_ephemeral", None)
        if callable(clear_active):
            await clear_active(
                guild_id=guild.id,
                user_id=interaction.user.id,
            )
        embed, view = build_game_embed(
            result,
            download_app_emoji=download_app_emoji,
            requirements_button_emoji=requirements_button_emoji,
            requester_id=interaction.user.id,
            guild=guild,
            config_service=self.config_service,
            share_enabled=self.config_service.can_share_game(guild, interaction.user),
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
                guild_id=guild.id,
                user_id=interaction.user.id,
                delete_callback=interaction.delete_original_response,
            )


class WelcomePanelPersistentView(discord.ui.View):
    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        game_service: GameService,
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(
            CatalogButton(
                config_service=config_service,
                game_service=game_service,
                guild=None,
                emoji="📚",
            )
        )
        self.add_item(
            SurpriseMeButton(
                config_service=config_service,
                game_service=game_service,
                guild=None,
                emoji="🎲",
            )
        )


class CanalGroup(app_commands.Group):
    def __init__(
        self,
        bot: commands.Bot,
        config_service: GuildConfigService,
        game_service: GameService,
        stats_service: StatsService,
    ) -> None:
        super().__init__(
            name="canal",
            description="[ 🔐ADMIN ] Configuração do canal do bot.",
        )
        self.bot = bot
        self.config_service = config_service
        self.game_service = game_service
        self.stats_service = stats_service

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
        name="setar",
        description="[ 🔐ADMIN ] Define o canal usado pelo bot nas buscas por mensagem.",
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(canal="Canal onde o bot vai responder mensagens")
    async def setar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        self.config_service.set_bot_channel_id(interaction.guild.id, canal.id)
        welcome_message = await self._upsert_welcome_message(
            guild_id=interaction.guild.id,
            channel=canal,
        )
        LOGGER.info(
            "Bot channel set manually guild=%s channel=%s user=%s welcome_message=%s",
            interaction.guild.id,
            canal.id,
            interaction.user.id,
            welcome_message.id,
        )
        await interaction.response.send_message(
            f"Canal do bot configurado com sucesso: {canal.mention}",
            ephemeral=True,
        )

    @app_commands.command(
        name="atualizar",
        description="[ 🔐ADMIN ] Atualiza a mensagem principal do canal do bot.",
    )
    @app_commands.default_permissions(manage_channels=True)
    async def atualizar(self, interaction: discord.Interaction) -> None:
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

        welcome_message = await self._upsert_welcome_message(
            guild_id=interaction.guild.id,
            channel=channel,
        )
        LOGGER.info(
            "Bot channel welcome updated guild=%s channel=%s user=%s welcome_message=%s",
            interaction.guild.id,
            channel.id,
            interaction.user.id,
            welcome_message.id,
        )
        await interaction.response.send_message(
            f"Mensagem principal atualizada em {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ver",
        description="[ 🔐ADMIN ] Mostra qual canal está configurado para busca por mensagem.",
    )
    async def ver(self, interaction: discord.Interaction) -> None:
        channel_id = self.config_service.get_bot_channel_id(interaction.guild.id)
        if channel_id is None:
            await interaction.response.send_message(
                "Nenhum canal do bot foi configurado ainda.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        mention = channel.mention if channel else f"`{channel_id}`"
        LOGGER.info(
            "Bot channel viewed guild=%s channel=%s user=%s",
            interaction.guild.id,
            channel_id,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"Canal atual do bot: {mention}",
            ephemeral=True,
        )

    @app_commands.command(
        name="criar",
        description="[ 🔐ADMIN ] Cria um canal novo e já define ele como canal oficial do bot.",
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(nome="Nome do canal a ser criado")
    async def criar(
        self,
        interaction: discord.Interaction,
        nome: str = "rumble-bot",
    ) -> None:
        existing_channel = discord.utils.get(interaction.guild.text_channels, name=nome)
        channel = existing_channel
        if channel is None:
            channel = await interaction.guild.create_text_channel(nome)

        self.config_service.set_bot_channel_id(interaction.guild.id, channel.id)
        welcome_message = await self._upsert_welcome_message(
            guild_id=interaction.guild.id,
            channel=channel,
        )
        LOGGER.info(
            "Bot channel created/set guild=%s channel=%s user=%s name=%r welcome_message=%s",
            interaction.guild.id,
            channel.id,
            interaction.user.id,
            nome,
            welcome_message.id,
        )
        await interaction.response.send_message(
            f"Canal criado/configurado com sucesso: {channel.mention}",
            ephemeral=True,
        )

    async def _upsert_welcome_message(
        self,
        *,
        guild_id: int,
        channel: discord.TextChannel,
    ) -> discord.Message:
        welcome_message_id = self.config_service.get_welcome_message_id(guild_id)
        panel_role_id = self.config_service.get_panel_role_id(guild_id)
        panel_role = channel.guild.get_role(panel_role_id) if panel_role_id else None
        panel_role_mention = panel_role.mention if panel_role else None
        search_command_mention = "/buscar jogo"
        resolve_command_mention = getattr(self.bot, "resolve_command_mention", None)
        if callable(resolve_command_mention):
            search_command_mention = await resolve_command_mention(
                "buscar jogo",
                guild_id=guild_id,
            )
        download_button_emoji = self._get_ui_emoji(channel.guild, "download_client_button")
        catalog_button_emoji = self._get_ui_emoji(channel.guild, "catalog_button")
        stats = self.stats_service.get_stats()
        formatted_last_scrape_at = self.stats_service.format_last_scrape_at(stats)
        last_scrape_unix = self.stats_service.get_last_scrape_unix(stats)
        title_emoji = str(download_button_emoji) if download_button_emoji else "🎮"
        surprise_button_emoji = self._get_ui_emoji(channel.guild, "surprise_me_button")
        total_games_text = f"{stats.total_games:,}".replace(",", ".") if stats else "N/A"
        recent_games_text = build_recent_games_text(stats)
        embed = build_welcome_embed(
            search_command_mention=search_command_mention,
            total_games_text=total_games_text,
            recent_games_text=recent_games_text,
            last_updated_text=formatted_last_scrape_at,
            last_updated_timestamp=last_scrape_unix,
            title_emoji=title_emoji,
        )
        view = WelcomePanelView(
            bot=self.bot,
            config_service=self.config_service,
            game_service=self.game_service,
            guild=channel.guild,
            download_button_emoji=download_button_emoji,
            catalog_button_emoji=catalog_button_emoji,
            surprise_button_emoji=surprise_button_emoji,
        )
        allowed_mentions = discord.AllowedMentions(roles=True)

        if welcome_message_id is not None:
            try:
                message = await channel.fetch_message(welcome_message_id)
                logo_file = build_welcome_logo_file()
                attachments = [logo_file] if logo_file is not None else []
                await message.edit(
                    content=panel_role_mention,
                    embed=embed,
                    attachments=attachments,
                    view=view,
                    allowed_mentions=allowed_mentions,
                )
                self.config_service.set_welcome_message_id(guild_id, message.id)
                return message
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                LOGGER.warning(
                    "Failed to edit stored welcome message guild=%s channel=%s message=%s",
                    guild_id,
                    channel.id,
                    welcome_message_id,
                )

        logo_file = build_welcome_logo_file()
        if logo_file is not None:
            message = await channel.send(
                content=panel_role_mention,
                embed=embed,
                file=logo_file,
                view=view,
                allowed_mentions=allowed_mentions,
            )
        else:
            message = await channel.send(
                content=panel_role_mention,
                embed=embed,
                view=view,
                allowed_mentions=allowed_mentions,
            )
        self.config_service.set_welcome_message_id(guild_id, message.id)
        return message

    def _get_ui_emoji(
        self,
        guild: discord.Guild,
        key: str,
    ) -> discord.Emoji | discord.PartialEmoji | str | None:
        emoji_value = self.config_service.get_ui_emoji(guild.id, key)
        if emoji_value is None:
            return None

        if emoji_value.startswith("id:"):
            try:
                emoji_id = int(emoji_value.split(":", 1)[1])
            except ValueError:
                return None
            emoji = guild.get_emoji(emoji_id) or self.bot.get_emoji(emoji_id)
            return emoji

        return emoji_value


class AdminCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        config_service: GuildConfigService,
        game_service: GameService,
        stats_service: StatsService,
    ) -> None:
        self.bot = bot
        self.config_service = config_service
        self.game_service = game_service
        self.stats_service = stats_service
        self.canal_group = CanalGroup(bot, config_service, game_service, stats_service)

    async def cog_load(self) -> None:
        self.bot.add_view(
            WelcomePanelPersistentView(
                config_service=self.config_service,
                game_service=self.game_service,
            )
        )
        self.bot.tree.add_command(self.canal_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.canal_group.name, type=self.canal_group.type)

    async def refresh_all_welcome_messages(self) -> int:
        refreshed = 0
        for guild_id in self.config_service.get_configured_guild_ids():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            channel_id = self.config_service.get_bot_channel_id(guild_id)
            if channel_id is None:
                continue

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                await self.canal_group._upsert_welcome_message(
                    guild_id=guild_id,
                    channel=channel,
                )
                refreshed += 1
            except discord.HTTPException as exc:
                LOGGER.warning(
                    "Failed to auto-refresh welcome message guild=%s channel=%s error=%s",
                    guild_id,
                    channel_id,
                    exc,
                )

        return refreshed

    async def cleanup_configured_bot_channels(self) -> int:
        deleted_messages = 0
        for guild_id in self.config_service.get_configured_guild_ids():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            channel_id = self.config_service.get_bot_channel_id(guild_id)
            if channel_id is None:
                continue

            welcome_message_id = self.config_service.get_welcome_message_id(guild_id)
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

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
                            "Failed to delete startup channel message guild=%s channel=%s message=%s error=%s",
                            guild_id,
                            channel_id,
                            message.id,
                            exc,
                        )
            except discord.HTTPException as exc:
                LOGGER.warning(
                    "Failed to inspect configured bot channel guild=%s channel=%s error=%s",
                    guild_id,
                    channel_id,
                    exc,
                )

        return deleted_messages


async def setup(bot: commands.Bot) -> None:
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    game_service: GameService = bot.game_service  # type: ignore[attr-defined]
    stats_service: StatsService = bot.stats_service  # type: ignore[attr-defined]
    await bot.add_cog(AdminCog(bot, config_service, game_service, stats_service))
