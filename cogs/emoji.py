from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from services.guild_config_service import GuildConfigService

LOGGER = logging.getLogger(__name__)
EMOJI_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]")
CUSTOM_EMOJI_INPUT_PATTERN = re.compile(r"<a?:[A-Za-z0-9_]+:(\d+)>")
UI_EMOJI_KEYS = {
    "info": "Informação",
    "warning": "Aviso",
    "error": "Erro",
    "success": "Sucesso",
    "loading": "Carregamento",
    "download_client_button": "Botão Baixar Client",
    "catalog_button": "Botão Catálogo",
    "download_app_button": "Botão Baixar no App",
    "requirements_button": "Botão Requisitos",
    "confirm_button": "Botão Confirmar",
    "decline_button": "Botão Recusar",
    "surprise_me_button": "Botão Surpreenda-me",
}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".gif",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}


def _normalize_emoji_name(raw_name: str) -> str:
    cleaned = EMOJI_NAME_PATTERN.sub("_", raw_name).strip("_")
    if not cleaned:
        cleaned = "emoji"
    return cleaned[:32]


def _extract_custom_emoji_id(raw_value: str) -> int | None:
    value = raw_value.strip()
    if not value:
        return None

    match = CUSTOM_EMOJI_INPUT_PATTERN.fullmatch(value)
    if match is not None:
        return int(match.group(1))

    if value.isdigit():
        return int(value)

    return None


def _render_configured_emoji(guild: discord.Guild, emoji_value: str | None) -> str:
    if not emoji_value:
        return "Não configurado"

    if emoji_value.startswith("id:"):
        try:
            emoji_id = int(emoji_value.split(":", 1)[1])
        except ValueError:
            return "Não configurado"
        emoji = guild.get_emoji(emoji_id)
        return str(emoji) if emoji is not None else "Emoji removido"

    return emoji_value


def _build_emoji_config_embed(
    guild: discord.Guild,
    config_service: GuildConfigService,
    selected_key: str,
) -> discord.Embed:
    ui_emojis = config_service.get_ui_emojis(guild.id)
    lines = []
    for key, label in UI_EMOJI_KEYS.items():
        rendered = _render_configured_emoji(guild, ui_emojis.get(key))
        prefix = ">" if key == selected_key else "-"
        lines.append(f"{prefix} `{key}` ({label}): {rendered}")

    embed = discord.Embed(
        title="Configuração de emojis do bot",
        description=(
            "Escolha a categoria e depois selecione qual emoji do servidor será "
            "usado nela. Se preferir, você também pode informar o emoji manualmente."
        ),
        color=discord.Color.red(),
    )
    embed.add_field(name="Categorias", value="\n".join(lines), inline=False)
    embed.set_footer(
        text=(
            "A interface usa `download_client_button`, `catalog_button`, `download_app_button`, "
            "`requirements_button`, `confirm_button`, `decline_button`, "
            "`surprise_me_button` e os status como `info`."
        )
    )
    return embed


class EmojiCategorySelect(discord.ui.Select):
    def __init__(self, view_ref: "EmojiConfigView") -> None:
        options = [
            discord.SelectOption(
                label=label,
                value=key,
                default=(key == view_ref.selected_key),
            )
            for key, label in UI_EMOJI_KEYS.items()
        ]
        super().__init__(
            placeholder="Selecione a categoria",
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

        self.view_ref.selected_key = self.values[0]
        await interaction.response.edit_message(
            embed=_build_emoji_config_embed(
                self.view_ref.guild,
                self.view_ref.config_service,
                self.view_ref.selected_key,
            ),
            view=EmojiConfigView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
                selected_key=self.view_ref.selected_key,
            ),
        )


class EmojiValueSelect(discord.ui.Select):
    def __init__(self, view_ref: "EmojiConfigView") -> None:
        emoji_options = [
            discord.SelectOption(
                label=f"{emoji.name} {'(animado)' if emoji.animated else '(estático)'}"[:100],
                value=str(emoji.id),
            )
            for emoji in view_ref.guild.emojis[:25]
        ]
        super().__init__(
            placeholder="Selecione o emoji do servidor",
            min_values=1,
            max_values=1,
            options=emoji_options or [
                discord.SelectOption(
                    label="Nenhum emoji disponível",
                    value="0",
                )
            ],
            disabled=not emoji_options,
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

        emoji_id = int(self.values[0])
        self.view_ref.config_service.set_ui_emoji(
            self.view_ref.guild.id,
            self.view_ref.selected_key,
            f"id:{emoji_id}",
        )
        LOGGER.info(
            "UI emoji configured guild=%s key=%s emoji=%s user=%s",
            self.view_ref.guild.id,
            self.view_ref.selected_key,
            emoji_id,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=_build_emoji_config_embed(
                self.view_ref.guild,
                self.view_ref.config_service,
                self.view_ref.selected_key,
            ),
            view=EmojiConfigView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
                selected_key=self.view_ref.selected_key,
            ),
        )


class ManualEmojiModal(discord.ui.Modal, title="Configurar emoji manualmente"):
    emoji_input = discord.ui.TextInput(
        label="Emoji ou ID",
        placeholder="🎊 ou <:info:123456789012345678> ou 123456789012345678",
        required=True,
        max_length=64,
    )

    def __init__(self, view_ref: "EmojiConfigView") -> None:
        super().__init__()
        self.view_ref = view_ref

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.view_ref.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        raw_value = self.emoji_input.value.strip()
        emoji_id = _extract_custom_emoji_id(raw_value)
        if emoji_id is not None:
            emoji = self.view_ref.guild.get_emoji(emoji_id)
            if emoji is None:
                await interaction.response.send_message(
                    "Não encontrei esse emoji neste servidor.",
                    ephemeral=True,
                )
                return
            stored_value = f"id:{emoji.id}"
        else:
            stored_value = raw_value

        self.view_ref.config_service.set_ui_emoji(
            self.view_ref.guild.id,
            self.view_ref.selected_key,
            stored_value,
        )
        LOGGER.info(
            "UI emoji configured manually guild=%s key=%s emoji=%r user=%s",
            self.view_ref.guild.id,
            self.view_ref.selected_key,
            stored_value,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=_build_emoji_config_embed(
                self.view_ref.guild,
                self.view_ref.config_service,
                self.view_ref.selected_key,
            ),
            view=EmojiConfigView(
                config_service=self.view_ref.config_service,
                guild=self.view_ref.guild,
                requester_id=self.view_ref.requester_id,
                selected_key=self.view_ref.selected_key,
            ),
        )


class EmojiConfigView(discord.ui.View):
    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        guild: discord.Guild,
        requester_id: int,
        selected_key: str = "info",
    ) -> None:
        super().__init__(timeout=300)
        self.config_service = config_service
        self.guild = guild
        self.requester_id = requester_id
        self.selected_key = selected_key
        self.add_item(EmojiCategorySelect(self))
        self.add_item(EmojiValueSelect(self))

        has_selected_emoji = (
            self.config_service.get_ui_emoji(guild.id, selected_key) is not None
        )
        self.clear_category.disabled = not has_selected_emoji

    @discord.ui.button(
        label="Inserir manualmente",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def set_manual_category(
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

        await interaction.response.send_modal(ManualEmojiModal(self))

    @discord.ui.button(label="Limpar categoria", style=discord.ButtonStyle.danger, row=2)
    async def clear_category(
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

        self.config_service.remove_ui_emoji(self.guild.id, self.selected_key)
        LOGGER.info(
            "UI emoji cleared guild=%s key=%s user=%s",
            self.guild.id,
            self.selected_key,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=_build_emoji_config_embed(
                self.guild,
                self.config_service,
                self.selected_key,
            ),
            view=EmojiConfigView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
                selected_key=self.selected_key,
            ),
        )


class EmojiGroup(app_commands.Group):
    def __init__(self, config_service: GuildConfigService) -> None:
        super().__init__(
            name="emoji",
            description="[ 🔐ADMIN ] Gerencia os emojis do servidor.",
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
        name="adicionar",
        description="[ 🔐ADMIN ] Adiciona um emoji por URL ou arquivo enviado.",
    )
    @app_commands.describe(
        url="URL do emoji",
        arquivo="Arquivo do emoji (gif, png, jpg, jpeg, webp, bmp)",
        nome="Nome do emoji no servidor",
    )
    async def adicionar(
        self,
        interaction: discord.Interaction,
        url: str | None = None,
        arquivo: discord.Attachment | None = None,
        nome: str | None = None,
    ) -> None:
        guild = interaction.guild
        assert guild is not None

        if not url and arquivo is None:
            await interaction.response.send_message(
                "Informe uma URL ou envie um arquivo para adicionar o emoji.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        image_bytes: bytes
        fallback_name: str

        try:
            if arquivo is not None:
                suffix = ""
                if "." in arquivo.filename:
                    suffix = "." + arquivo.filename.rsplit(".", 1)[-1].lower()
                if suffix not in ALLOWED_ATTACHMENT_EXTENSIONS:
                    await interaction.followup.send(
                        "Formato de arquivo não suportado. Use gif, png, jpg, jpeg, webp ou bmp.",
                        ephemeral=True,
                    )
                    return

                image_bytes = await arquivo.read()
                fallback_name = arquivo.filename.rsplit(".", 1)[0] or "emoji"
            else:
                assert url is not None
                parsed_url = urlparse(url)
                fallback_name = parsed_url.path.rsplit("/", 1)[-1].split(".", 1)[0] or "emoji"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            await interaction.followup.send(
                                "Não consegui baixar a imagem informada.",
                                ephemeral=True,
                            )
                            return
                        image_bytes = await response.read()
        except aiohttp.ClientError:
            LOGGER.exception(
                "Failed to download emoji guild=%s user=%s url=%r",
                guild.id,
                interaction.user.id,
                url,
            )
            await interaction.followup.send(
                "Não consegui baixar a imagem do emoji.",
                ephemeral=True,
            )
            return

        emoji_name = _normalize_emoji_name(nome or fallback_name)

        try:
            created_emoji = await guild.create_custom_emoji(
                name=emoji_name,
                image=image_bytes,
                reason=f"Emoji adicionado por {interaction.user}",
            )
        except discord.HTTPException as exc:
            LOGGER.exception(
                "Failed to create emoji guild=%s user=%s source_url=%r filename=%r",
                guild.id,
                interaction.user.id,
                url,
                arquivo.filename if arquivo else None,
            )
            await interaction.followup.send(
                f"Não consegui adicionar o emoji: {exc}",
                ephemeral=True,
            )
            return

        static_count = sum(1 for emoji in guild.emojis if not emoji.animated)
        animated_count = sum(1 for emoji in guild.emojis if emoji.animated)
        remaining_static = max(guild.emoji_limit - static_count, 0)
        remaining_animated = max(guild.emoji_limit - animated_count, 0)

        LOGGER.info(
            "Emoji added guild=%s user=%s emoji=%s animated=%s",
            guild.id,
            interaction.user.id,
            created_emoji.id,
            created_emoji.animated,
        )
        await interaction.followup.send(
            f"Emoji adicionado com sucesso: {created_emoji}\n\n"
            f"Slots restantes de emojis estáticos: {remaining_static}\n"
            f"Slots restantes de emojis animados: {remaining_animated}",
            ephemeral=True,
        )

    @app_commands.command(
        name="config",
        description="[ 🔐ADMIN ] Configura quais emojis do servidor o bot deve usar na interface.",
    )
    async def config(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        await interaction.response.send_message(
            embed=_build_emoji_config_embed(guild, self.config_service, "info"),
            view=EmojiConfigView(
                config_service=self.config_service,
                guild=guild,
                requester_id=interaction.user.id,
                selected_key="info",
            ),
            ephemeral=True,
        )


class EmojiCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config_service: GuildConfigService) -> None:
        self.bot = bot
        self.config_service = config_service
        self.emoji_group = EmojiGroup(config_service)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.emoji_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.emoji_group.name, type=self.emoji_group.type)


async def setup(bot: commands.Bot) -> None:
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    await bot.add_cog(EmojiCog(bot, config_service))
