from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import discord

from domain.models import CatalogStats, GameDownload, SearchResult
from services.guild_config_service import GuildConfigService
from utils.gr_link_encoder import GRLinkPayload

BASE_DIR = Path(__file__).resolve().parents[1]
RUMBLE_LOGO_FILE = BASE_DIR / "logo.png"
RUMBLE_LOGO_ATTACHMENT_NAME = "logo.png"
CLIENT_RELEASES_URL = (
    "https://github.com/zKauaFerreira/The-Gaming-Rumble/releases"
)
REQUIREMENTS_TRANSLATIONS_FILE = BASE_DIR / "requirements_translations.json"
SHARE_DURATION_PATTERN = re.compile(
    r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$",
    re.IGNORECASE,
)


class ChannelSelectionLayoutView(discord.ui.LayoutView):
    def __init__(self, query: str, results: list[SearchResult]) -> None:
        super().__init__(timeout=300)
        option_lines = [
            f"{index}. {result.game.title}"
            for index, result in enumerate(results, start=1)
        ]
        self.add_item(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    "## Qual jogo você está buscando?\n"
                    f"Busca enviada: `{query}`"
                ),
                accessory=discord.ui.Button(
                    label="Escolha abaixo",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                ),
            )
        )
        self.add_item(discord.ui.Separator())
        self.add_item(
            discord.ui.TextDisplay(
                "**Opções encontradas**\n" + "\n".join(option_lines)
            )
        )


def build_selection_embed(query: str, results: list[SearchResult]) -> discord.Embed:
    option_lines = [
        f"{index}. {result.game.title}"
        for index, result in enumerate(results, start=1)
    ]
    embed = discord.Embed(
        title="Qual jogo você está buscando?",
        description=(
            f"Busca enviada: `{query}`\n\n"
            "**Opções encontradas**\n" + "\n".join(option_lines)
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Selecione o jogo correto no menu abaixo.")
    return embed


def build_timed_selection_embed(
    query: str,
    results: list[SearchResult],
    *,
    expires_at_timestamp: int | None = None,
) -> discord.Embed:
    embed = build_selection_embed(query, results)
    if expires_at_timestamp is not None:
        embed.add_field(name="Expira", value=f"<t:{expires_at_timestamp}:R>", inline=False)
    return embed


def build_recent_games_text(stats: CatalogStats | None) -> str:
    latest_games = stats.latest_run_new_game_names if stats else []
    visible_latest_games = latest_games[:5]
    hidden_latest_games_count = max(len(latest_games) - len(visible_latest_games), 0)
    latest_games_lines = [f"• {game_name}" for game_name in visible_latest_games]
    if hidden_latest_games_count > 0:
        if latest_games_lines:
            latest_games_lines[-1] = f"{latest_games_lines[-1]}..."
        latest_games_lines.append(f"**+{hidden_latest_games_count}**")
    return "\n".join(latest_games_lines)


def build_exact_match_confirmation_embed(
    result: SearchResult,
    *,
    expires_at_timestamp: int | None = None,
) -> discord.Embed:
    game = result.game
    embed = discord.Embed(
        title=game.title,
        description="Esse é o jogo que você estava buscando?",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Confirmar busca",
        value="Use os botões abaixo para confirmar ou recusar.",
        inline=False,
    )
    if expires_at_timestamp is not None:
        embed.add_field(name="Expira", value=f"<t:{expires_at_timestamp}:R>", inline=False)
    if game.cover_url:
        embed.set_image(url=game.cover_url)
    return embed


def build_welcome_embed(
    search_command_mention: str,
    total_games_text: str,
    recent_games_text: str,
    last_updated_text: str | None,
    last_updated_timestamp: int | None,
    title_emoji: str | None = None,
) -> discord.Embed:
    title_prefix = f"{title_emoji} " if title_emoji else ""
    embed = discord.Embed(
        title=f"{title_prefix}Rumble Game Bot",
        description="Seu painel rápido para buscar e instalar jogos.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="**📌 Como usar:**",
        value=(
            "1. Instale o client oficial pelo botão abaixo\n"
            f"2. Use o comando {search_command_mention} ou digite o nome do jogo no chat\n"
            "3. O bot apaga sua mensagem e retorna o jogo encontrado"
        ),
        inline=False,
    )
    embed.add_field(
        name="**📚 Biblioteca:**",
        value=f"{total_games_text} jogos disponíveis",
        inline=False,
    )
    if recent_games_text.strip():
        embed.add_field(
            name="**🆕 Adicionados recentemente:**",
            value=recent_games_text,
            inline=False,
        )
    embed.add_field(
        name="**🌐 Fonte:**",
        value="Online-Fix.me + Gaming Rumble",
        inline=False,
    )
    if RUMBLE_LOGO_FILE.exists():
        embed.set_thumbnail(url=f"attachment://{RUMBLE_LOGO_ATTACHMENT_NAME}")
    if last_updated_timestamp is not None:
        embed.timestamp = datetime.fromtimestamp(last_updated_timestamp, tz=timezone.utc)
        embed.set_footer(text="Atualizado")
    return embed


def build_welcome_logo_file() -> discord.File | None:
    if not RUMBLE_LOGO_FILE.exists():
        return None
    return discord.File(RUMBLE_LOGO_FILE, filename=RUMBLE_LOGO_ATTACHMENT_NAME)


def build_selection_view(query: str, results: list[SearchResult]) -> discord.ui.LayoutView:
    return ChannelSelectionLayoutView(query=query, results=results)


def build_admin_roles_embed(guild: discord.Guild, role_ids: list[int]) -> discord.Embed:
    lines = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role is not None:
            lines.append(f"- {role.mention}")

    if not lines:
        lines.append("- Nenhum cargo configurado")

    embed = discord.Embed(
        title="Cargos com acesso administrativo ao bot",
        description=(
            "Esses cargos podem usar `/canal`, `/ping`, `/config`, `/bot`, `/emoji` "
            "e todos os subcomandos relacionados."
        ),
        color=discord.Color.red(),
    )
    embed.add_field(name="Cargos permitidos", value="\n".join(lines), inline=False)
    embed.set_footer(
        text=(
            "Se nenhum cargo estiver configurado, somente o dono do servidor pode "
            "usar os comandos administrativos."
        )
    )
    return embed


def build_bot_settings_embed(
    guild: discord.Guild,
    delete_notice_after_seconds: int,
    ephemeral_game_result_seconds: int,
    panel_role_id: int | None,
    share_role_id: int | None,
) -> discord.Embed:
    role = guild.get_role(panel_role_id) if panel_role_id else None
    share_role = guild.get_role(share_role_id) if share_role_id else None
    embed = discord.Embed(
        title="Configurações gerais do bot",
        description="Ajuste o comportamento da mensagem principal e dos avisos automáticos.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Apagar aviso de permissão",
        value=f"{delete_notice_after_seconds} segundo(s)",
        inline=False,
    )
    embed.add_field(
        name="Confirmação da busca exata",
        value=f"{ephemeral_game_result_seconds} segundo(s)",
        inline=False,
    )
    embed.add_field(
        name="Cargo marcado acima da embed",
        value=role.mention if role else "Nenhum cargo configurado",
        inline=False,
    )
    embed.add_field(
        name="Cargo permitido para compartilhar jogo",
        value=share_role.mention if share_role else "Nenhum cargo configurado",
        inline=False,
    )
    return embed


def parse_share_duration(value: str) -> int | None:
    normalized = value.strip().lower()
    if normalized == "lifetime":
        return None
    if not normalized:
        raise ValueError("Informe uma duração.")

    match = SHARE_DURATION_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            "Formato inválido. Exemplos: 30s, 10m, 1h, 1h23s, 1h23m12s, 1d, 165d, 9888d, lifetime."
        )

    days, hours, minutes, seconds = (
        int(part) if part is not None else 0
        for part in match.groups()
    )
    total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if total_seconds <= 0:
        raise ValueError("A duração precisa ser maior que zero.")
    return total_seconds


def _resolve_game_update_timestamp(game: GameDownload) -> int | None:
    raw_update_date = str(game.raw.get("update_date") or "").strip()
    raw_last_update = str(game.raw.get("last_update") or "").strip()
    for raw_value in (raw_update_date, raw_last_update):
        if not raw_value:
            continue
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    return None


def _has_controller_support(game: GameDownload) -> bool:
    steam_payload = game.raw.get("steam")
    if not isinstance(steam_payload, dict):
        return False
    return steam_payload.get("controller_support") is not None


def _format_requirement_label(label: str) -> str:
    normalized = label.strip().replace("*", "").strip()
    replacements = {
        "Sistema Operativo": "Sistema Operacional",
        "Placa gráfica": "Placa de Vídeo",
    }
    return replacements.get(normalized, normalized)


@lru_cache(maxsize=1)
def _load_requirement_translation_map() -> dict[str, str]:
    if not REQUIREMENTS_TRANSLATIONS_FILE.exists():
        return {}

    try:
        payload = json.loads(REQUIREMENTS_TRANSLATIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    raw_replacements = payload.get("phrase_replacements", {})
    if not isinstance(raw_replacements, dict):
        return {}

    normalized_replacements: dict[str, str] = {}
    for source, target in raw_replacements.items():
        source_text = str(source).strip()
        target_text = str(target).strip()
        if source_text and target_text:
            normalized_replacements[source_text] = target_text
    return normalized_replacements


def _apply_requirement_translations(value: str) -> str:
    translated = value
    replacements = _load_requirement_translation_map()
    for source, target in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])"
        translated = re.sub(
            pattern,
            target,
            translated,
            flags=re.IGNORECASE,
        )
    return translated


def _normalize_requirement_value(value: str) -> str:
    normalized = value.strip()
    normalized = _apply_requirement_translations(normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _format_requirements_block(raw_text: object, *, fallback: str) -> str:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return fallback

    ignored_entries = {
        "Requer um sistema operativo e processador de 64 bits",
        "Requires a 64-bit processor and operating system",
    }
    allowed_labels = {
        "Sistema Operacional",
        "Processador",
        "Memória",
        "Placa de Vídeo",
        "Espaço no disco",
    }

    lines: list[str] = []
    for chunk in raw_text.split("\n\n"):
        entry = chunk.strip()
        if not entry or entry in {"Mínimos:", "Recomendados:"} or entry in ignored_entries:
            continue
        if ":" not in entry:
            continue
        label, value = entry.split(":", 1)
        formatted_label = _format_requirement_label(label)
        if formatted_label not in allowed_labels:
            continue
        lines.append(f"**{formatted_label}:**")
        lines.append(_normalize_requirement_value(value) or "N/A")

    if not lines:
        return fallback

    formatted = "\n".join(lines)
    return formatted if len(formatted) <= 1024 else f"{formatted[:1021].rstrip()}..."


def _get_pc_requirements(game: GameDownload) -> tuple[str, str]:
    steam_payload = game.raw.get("steam")
    if not isinstance(steam_payload, dict):
        return ("Não informado", "Não informado")
    requirements = steam_payload.get("pc_requirements")
    if not isinstance(requirements, dict):
        return ("Não informado", "Não informado")
    return (
        _format_requirements_block(requirements.get("minimum"), fallback="Não informado"),
        _format_requirements_block(requirements.get("recommended"), fallback="Não informado"),
    )


def _has_requirements_metadata(game: GameDownload) -> bool:
    minimum, recommended = _get_pc_requirements(game)
    return minimum != "Não informado" or recommended != "Não informado"


def build_game_main_embed(
    result: SearchResult,
    *,
    expires_at_timestamp: int | None = None,
) -> discord.Embed:
    game = result.game
    update_timestamp = _resolve_game_update_timestamp(game)
    update_value = f"<t:{update_timestamp}:R>" if update_timestamp is not None else "N/A"

    embed = discord.Embed(
        title=game.title,
        url=game.url,
        description=(game.description or "Sem descrição adicional no catálogo.")[:4000],
        color=discord.Color.blue(),
    )
    embed.add_field(name="Tamanho:", value=game.file_size or "N/A", inline=True)
    embed.add_field(name="Última atualização:", value=update_value, inline=True)
    embed.add_field(
        name="Controle?",
        value="Sim" if _has_controller_support(game) else "Não",
        inline=True,
    )
    if expires_at_timestamp is not None:
        embed.add_field(
            name="Mensagem expira",
            value=f"<t:{expires_at_timestamp}:R>",
            inline=False,
        )
    if game.cover_url:
        embed.set_image(url=game.cover_url)
    embed.set_footer(text="Fonte: online-fix.me")
    return embed


def build_game_requirements_embed(
    result: SearchResult,
    *,
    show_back_hint: bool = True,
) -> discord.Embed:
    game = result.game
    minimum_requirements, recommended_requirements = _get_pc_requirements(game)

    embed = discord.Embed(
        title=game.title,
        url=game.url,
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Requisitos mínimos:",
        value=minimum_requirements,
        inline=True,
    )
    embed.add_field(
        name="Requisitos recomendados:",
        value=recommended_requirements,
        inline=True,
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    if game.cover_url:
        embed.set_image(url=game.cover_url)
    if show_back_hint:
        embed.set_footer(text="Clique em Voltar para retornar aos dados do jogo")
    return embed


class ShareChannelSelect(discord.ui.ChannelSelect["ShareGameSetupView"]):
    def __init__(self) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Selecione o canal para compartilhar",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        if interaction.user.id != self.view.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse compartilhamento pode usar essa ação.",
                ephemeral=True,
            )
            return

        selected_channel = self.values[0]
        channel_id = getattr(selected_channel, "id", None)
        if channel_id is not None:
            resolved_channel = self.view.guild.get_channel(int(channel_id))
            if isinstance(resolved_channel, discord.TextChannel):
                self.view.selected_channel = resolved_channel
        await interaction.response.defer()


class ShareGameSetupView(discord.ui.View):
    def __init__(
        self,
        *,
        requester_id: int,
        result: SearchResult,
        guild: discord.Guild,
        config_service: GuildConfigService,
        duration_seconds: int | None,
        download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
    ) -> None:
        super().__init__(timeout=300)
        self.requester_id = requester_id
        self.result = result
        self.guild = guild
        self.config_service = config_service
        self.duration_seconds = duration_seconds
        self.download_app_emoji = download_app_emoji
        self.requirements_button_emoji = requirements_button_emoji
        self.selected_channel: discord.TextChannel | None = None
        self.add_item(ShareChannelSelect())

    @discord.ui.button(label="Compartilhar", style=discord.ButtonStyle.primary, emoji="📤", row=1)
    async def confirm_share(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse compartilhamento pode usar essa ação.",
                ephemeral=True,
            )
            return

        if self.selected_channel is None:
            await interaction.response.send_message(
                "Selecione um canal antes de compartilhar.",
                ephemeral=True,
            )
            return

        expires_at_timestamp = None
        if self.duration_seconds is not None:
            expires_at_timestamp = int(datetime.now(tz=timezone.utc).timestamp()) + self.duration_seconds

        embed = build_game_main_embed(
            self.result,
            expires_at_timestamp=expires_at_timestamp,
        )
        view = GameMessageView(
            self.result,
            download_app_emoji=self.download_app_emoji,
            requirements_button_emoji=self.requirements_button_emoji,
            main_embed=embed,
            requirements_embed=build_game_requirements_embed(self.result, show_back_hint=False),
            requester_id=self.requester_id,
            guild=self.guild,
            config_service=self.config_service,
            public_shared=True,
            share_enabled=False,
        )

        panel_role_id = self.config_service.get_panel_role_id(self.guild.id)
        panel_role = self.guild.get_role(panel_role_id) if panel_role_id else None
        content = panel_role.mention if panel_role else None
        allowed_mentions = discord.AllowedMentions(roles=True)

        shared_message = await self.selected_channel.send(
            content=content,
            embed=embed,
            view=view,
            allowed_mentions=allowed_mentions,
        )
        if self.duration_seconds is not None:
            async def _delete_later() -> None:
                try:
                    await asyncio.sleep(self.duration_seconds)
                    await shared_message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    return

            asyncio.create_task(_delete_later())

        await interaction.response.edit_message(
            content=f"Jogo compartilhado com sucesso em {self.selected_channel.mention}.",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def cancel_share(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse compartilhamento pode usar essa ação.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content="Compartilhamento cancelado.",
            embed=None,
            view=None,
        )


class ShareGameModal(discord.ui.Modal, title="Compartilhar jogo"):
    duration_input = discord.ui.TextInput(
        label="Duração da mensagem",
        placeholder="Ex.: 30s, 10m, 1h23m12s, 1d, lifetime",
        required=True,
        max_length=32,
    )

    def __init__(
        self,
        *,
        requester_id: int,
        result: SearchResult,
        guild: discord.Guild,
        config_service: GuildConfigService,
        download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None,
        requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None,
    ) -> None:
        super().__init__()
        self.requester_id = requester_id
        self.result = result
        self.guild = guild
        self.config_service = config_service
        self.download_app_emoji = download_app_emoji
        self.requirements_button_emoji = requirements_button_emoji

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse compartilhamento pode usar essa ação.",
                ephemeral=True,
            )
            return

        try:
            duration_seconds = parse_share_duration(self.duration_input.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            content=(
                "Selecione o canal onde a embed será enviada.\n"
                f"Duração escolhida: `{self.duration_input.value.strip()}`"
            ),
            view=ShareGameSetupView(
                requester_id=self.requester_id,
                result=self.result,
                guild=self.guild,
                config_service=self.config_service,
                duration_seconds=duration_seconds,
                download_app_emoji=self.download_app_emoji,
                requirements_button_emoji=self.requirements_button_emoji,
            ),
            ephemeral=True,
        )


class ShowRequirementsButton(discord.ui.Button["GameMessageView"]):
    def __init__(
        self,
        *,
        emoji: discord.Emoji | discord.PartialEmoji | str | None,
    ) -> None:
        super().__init__(
            label="Requisitos",
            style=discord.ButtonStyle.secondary,
            emoji=emoji or "📋",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        if self.view.public_shared:
            await interaction.response.send_message(
                embed=self.view.requirements_embed,
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=self.view.requirements_embed,
            view=GameMessageView(
                self.view.result,
                download_app_emoji=self.view.download_app_emoji,
                requirements_button_emoji=self.view.requirements_button_emoji,
                requirements_mode=True,
                main_embed=self.view.main_embed,
                requirements_embed=self.view.requirements_embed,
                requester_id=self.view.requester_id,
                guild=self.view.guild,
                config_service=self.view.config_service,
                public_shared=self.view.public_shared,
                share_enabled=self.view.share_enabled,
            ),
        )


class ShareGameButton(discord.ui.Button["GameMessageView"]):
    def __init__(self) -> None:
        super().__init__(
            label="Compartilhar",
            style=discord.ButtonStyle.secondary,
            emoji="📤",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        if self.view.requester_id is None or self.view.guild is None or self.view.config_service is None:
            await interaction.response.send_message(
                "Esse compartilhamento não está disponível aqui.",
                ephemeral=True,
            )
            return
        if interaction.user.id != self.view.requester_id:
            await interaction.response.send_message(
                "Só quem pediu o jogo pode compartilhar.",
                ephemeral=True,
            )
            return
        member = self.view.guild.get_member(interaction.user.id)
        if member is None or not self.view.config_service.can_share_game(self.view.guild, member):
            await interaction.response.send_message(
                "Você não tem permissão para compartilhar jogos neste servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            ShareGameModal(
                requester_id=self.view.requester_id,
                result=self.view.result,
                guild=self.view.guild,
                config_service=self.view.config_service,
                download_app_emoji=self.view.download_app_emoji,
                requirements_button_emoji=self.view.requirements_button_emoji,
            )
        )


class BackToGameButton(discord.ui.Button["GameMessageView"]):
    def __init__(self) -> None:
        super().__init__(
            label="Voltar",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await interaction.response.edit_message(
            embed=self.view.main_embed,
            view=GameMessageView(
                self.view.result,
                download_app_emoji=self.view.download_app_emoji,
                requirements_button_emoji=self.view.requirements_button_emoji,
                requirements_mode=False,
                main_embed=self.view.main_embed,
                requirements_embed=self.view.requirements_embed,
                requester_id=self.view.requester_id,
                guild=self.view.guild,
                config_service=self.view.config_service,
                public_shared=self.view.public_shared,
                share_enabled=self.view.share_enabled,
            ),
        )


class GameMessageView(discord.ui.View):
    def __init__(
        self,
        result: SearchResult,
        *,
        download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None = None,
        requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None = None,
        requirements_mode: bool = False,
        main_embed: discord.Embed | None = None,
        requirements_embed: discord.Embed | None = None,
        requester_id: int | None = None,
        guild: discord.Guild | None = None,
        config_service: GuildConfigService | None = None,
        public_shared: bool = False,
        share_enabled: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        self.result = result
        self.download_app_emoji = download_app_emoji
        self.requirements_button_emoji = requirements_button_emoji
        self.requester_id = requester_id
        self.guild = guild
        self.config_service = config_service
        self.public_shared = public_shared
        self.share_enabled = share_enabled
        self.main_embed = main_embed or build_game_main_embed(result)
        self.requirements_embed = requirements_embed or build_game_requirements_embed(
            result,
            show_back_hint=not public_shared,
        )

        if requirements_mode:
            self.add_item(BackToGameButton())
            return

        payload = GRLinkPayload.from_game(result.game)
        self.add_item(
            discord.ui.Button(
                label="Baixar no App",
                style=discord.ButtonStyle.green,
                url=payload.to_url(),
                emoji=download_app_emoji or "🎮",
            )
        )
        if _has_requirements_metadata(result.game):
            self.add_item(
                ShowRequirementsButton(
                    emoji=requirements_button_emoji,
                )
            )
        if (
            not public_shared
            and share_enabled
            and requester_id is not None
            and guild is not None
            and config_service is not None
        ):
            self.add_item(ShareGameButton())


def build_game_embed(
    result: SearchResult,
    *,
    download_app_emoji: discord.Emoji | discord.PartialEmoji | str | None = None,
    requirements_button_emoji: discord.Emoji | discord.PartialEmoji | str | None = None,
    requester_id: int | None = None,
    guild: discord.Guild | None = None,
    config_service: GuildConfigService | None = None,
    share_enabled: bool = True,
) -> tuple[discord.Embed, discord.ui.View]:
    main_embed = build_game_main_embed(result)
    requirements_embed = build_game_requirements_embed(result)
    return (
        main_embed,
        GameMessageView(
            result,
            download_app_emoji=download_app_emoji,
            requirements_button_emoji=requirements_button_emoji,
            requirements_mode=False,
            main_embed=main_embed,
            requirements_embed=requirements_embed,
            requester_id=requester_id,
            guild=guild,
            config_service=config_service,
            share_enabled=share_enabled,
        ),
    )
