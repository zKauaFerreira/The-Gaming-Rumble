from __future__ import annotations

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from services.guild_config_service import GuildConfigService
from utils.discord_utils import build_admin_roles_embed, parse_share_duration

LOGGER = logging.getLogger(__name__)
ACTIVITY_LINE_PATTERN = re.compile(r"^(?P<message>.*?)(?:\s*\[(?P<duration>[^\]]+)\])?$")
ACTIVITY_PLACEHOLDERS = (
    "`{{total_games}}`",
    "`{{new_games_count}}`",
    "`{{latest_game}}`",
    "`{{latest_update}}`",
    "`{{servers}}`",
    "`{{users}}`",
    "`{{latency_ms}}`",
)


def _format_activity_messages(items: list[dict[str, int | str | None]]) -> str:
    if not items:
        return "Nenhuma mensagem configurada"

    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        message = str(item.get("message", "")).strip()
        duration_seconds = item.get("duration_seconds")
        if duration_seconds is None:
            lines.append(f"{index}. {message}")
        else:
            lines.append(f"{index}. {message} [{duration_seconds}s]")
    return "\n".join(lines)


def _build_activity_messages_embed(
    guild: discord.Guild,
    config_service: GuildConfigService,
) -> discord.Embed:
    items = config_service.get_activity_messages(guild.id)
    embed = discord.Embed(
        title="Mensagens rotativas de atividade",
        description=(
            "Configure as mensagens que aparecem no status do bot.\n"
            "Use uma linha por mensagem no formato `Mensagem [20s]`.\n"
            "Se houver apenas uma mensagem, ela fica fixa e não rotaciona.\n"
            "Envie vazio para limpar tudo.\n\n"
            "Placeholders disponíveis:\n"
            f"{', '.join(ACTIVITY_PLACEHOLDERS)}"
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Mensagens atuais",
        value=_format_activity_messages(items),
        inline=False,
    )
    return embed


def _build_activity_placeholder_preview(interaction: discord.Interaction) -> dict[str, str]:
    stats_service = getattr(interaction.client, "stats_service", None)
    stats = stats_service.get_stats() if stats_service is not None else None
    latest_games = stats.latest_run_new_game_names if stats else []
    total_games = stats.total_games if stats else 0
    latest_update = stats_service.format_last_scrape_at(stats) if stats_service is not None and stats else None
    guilds = getattr(interaction.client, "guilds", [])
    users_total = sum(guild.member_count or 0 for guild in guilds)
    latency_ms = round(getattr(interaction.client, "latency", 0) * 1000)

    return {
        "{{total_games}}": f"{total_games:,}".replace(",", "."),
        "{{new_games_count}}": str(len(latest_games)),
        "{{latest_game}}": latest_games[0] if latest_games else "N/A",
        "{{latest_update}}": latest_update or "N/A",
        "{{servers}}": str(len(guilds)),
        "{{users}}": f"{users_total:,}".replace(",", "."),
        "{{latency_ms}}": str(latency_ms),
    }


class ActivityMessagesModal(discord.ui.Modal, title="Editar mensagens de atividade"):
    content = discord.ui.TextInput(
        label="Mensagens",
        style=discord.TextStyle.paragraph,
        placeholder="Mensagem 1 [20s]\nMensagem 2 [11s]",
        required=False,
        max_length=4000,
    )

    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        guild: discord.Guild,
    ) -> None:
        super().__init__()
        self.config_service = config_service
        self.guild = guild
        existing_items = self.config_service.get_activity_messages(guild.id)
        self.content.default = "\n".join(
            (
                f"{item['message']} [{item['duration_seconds']}s]"
                if item.get("duration_seconds") is not None
                else str(item["message"])
            )
            for item in existing_items
        )[:4000]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        placeholder_preview = _build_activity_placeholder_preview(interaction)
        raw_lines = [
            line.strip()
            for line in self.content.value.splitlines()
            if line.strip()
        ]
        if not raw_lines:
            self.config_service.set_activity_messages(self.guild.id, [])
            LOGGER.info(
                "Activity messages cleared guild=%s user=%s",
                self.guild.id,
                interaction.user.id,
            )
            await interaction.response.send_message(
                embed=_build_activity_messages_embed(self.guild, self.config_service),
                ephemeral=True,
            )
            return

        parsed_items: list[dict[str, int | str | None]] = []
        for line in raw_lines:
            match = ACTIVITY_LINE_PATTERN.fullmatch(line)
            if match is None:
                await interaction.response.send_message(
                    f"Formato inválido na linha: `{line}`",
                    ephemeral=True,
                )
                return

            message = (match.group("message") or "").strip()
            duration_text = (match.group("duration") or "").strip()
            if not message:
                await interaction.response.send_message(
                    f"A mensagem está vazia na linha: `{line}`",
                    ephemeral=True,
                )
                return
            if len(message) > 128:
                await interaction.response.send_message(
                    f"A mensagem `{message[:40]}...` passou de 128 caracteres.",
                    ephemeral=True,
                )
                return
            rendered_preview = message
            for key, value in placeholder_preview.items():
                rendered_preview = rendered_preview.replace(key, value)
            if len(rendered_preview) > 128:
                await interaction.response.send_message(
                    f"A mensagem renderizada `{rendered_preview[:60]}...` passou de 128 caracteres.",
                    ephemeral=True,
                )
                return

            duration_seconds: int | None = None
            if duration_text:
                try:
                    parsed_duration = parse_share_duration(duration_text)
                except ValueError as exc:
                    await interaction.response.send_message(
                        f"Linha `{line}` inválida: {exc}",
                        ephemeral=True,
                    )
                    return
                if parsed_duration is None:
                    await interaction.response.send_message(
                        f"`lifetime` não é válido para atividade rotativa na linha: `{line}`",
                        ephemeral=True,
                    )
                    return
                duration_seconds = parsed_duration

            parsed_items.append(
                {
                    "message": message,
                    "duration_seconds": duration_seconds,
                }
            )

        if len(parsed_items) > 1:
            missing_duration = [
                item["message"]
                for item in parsed_items
                if item["duration_seconds"] is None
            ]
            if missing_duration:
                await interaction.response.send_message(
                    "Quando houver mais de uma mensagem, todas precisam ter duração. "
                    "Exemplo: `Mensagem [20s]`.",
                    ephemeral=True,
                )
                return

        self.config_service.set_activity_messages(self.guild.id, parsed_items)
        LOGGER.info(
            "Activity messages updated guild=%s user=%s count=%s",
            self.guild.id,
            interaction.user.id,
            len(parsed_items),
        )

        refresh_presence = getattr(interaction.client, "refresh_rotating_activity", None)
        if callable(refresh_presence):
            await refresh_presence()

        await interaction.response.send_message(
            embed=_build_activity_messages_embed(self.guild, self.config_service),
            ephemeral=True,
        )


class AdminRolePicker(discord.ui.RoleSelect):
    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        guild: discord.Guild,
        requester_id: int,
    ) -> None:
        super().__init__(
            placeholder="Selecione um cargo para adicionar",
            min_values=1,
            max_values=1,
        )
        self.config_service = config_service
        self.guild = guild
        self.requester_id = requester_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        selected_role = self.values[0]
        self.config_service.add_admin_role(self.guild.id, selected_role.id)
        LOGGER.info(
            "Admin role added guild=%s role=%s user=%s",
            self.guild.id,
            selected_role.id,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=build_admin_roles_embed(
                self.guild,
                self.config_service.get_admin_role_ids(self.guild.id),
            ),
            view=AdminRolesView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )


class AdminRoleRemoveSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        config_service: GuildConfigService,
        guild: discord.Guild,
        requester_id: int,
    ) -> None:
        self.config_service = config_service
        self.guild = guild
        self.requester_id = requester_id
        role_ids = self.config_service.get_admin_role_ids(guild.id)
        options = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role is not None:
                options.append(
                    discord.SelectOption(
                        label=role.name[:100],
                        value=str(role.id),
                    )
                )

        super().__init__(
            placeholder="Selecione um cargo para remover",
            min_values=1,
            max_values=1,
            options=options or [
                discord.SelectOption(label="Nenhum cargo configurado", value="0")
            ],
            disabled=not options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Só quem abriu esse painel pode usar essa ação.",
                ephemeral=True,
            )
            return

        role_id = int(self.values[0])
        self.config_service.remove_admin_role(self.guild.id, role_id)
        LOGGER.info(
            "Admin role removed guild=%s role=%s user=%s",
            self.guild.id,
            role_id,
            interaction.user.id,
        )
        await interaction.response.edit_message(
            embed=build_admin_roles_embed(
                self.guild,
                self.config_service.get_admin_role_ids(self.guild.id),
            ),
            view=AdminRolesView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )


class AdminRoleAddView(discord.ui.View):
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
        self.add_item(
            AdminRolePicker(
                config_service=config_service,
                guild=guild,
                requester_id=requester_id,
            )
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def back(
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

        await interaction.response.edit_message(
            embed=build_admin_roles_embed(
                self.guild,
                self.config_service.get_admin_role_ids(self.guild.id),
            ),
            view=AdminRolesView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )


class AdminRoleRemoveView(discord.ui.View):
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
        self.add_item(
            AdminRoleRemoveSelect(
                config_service=config_service,
                guild=guild,
                requester_id=requester_id,
            )
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def back(
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

        await interaction.response.edit_message(
            embed=build_admin_roles_embed(
                self.guild,
                self.config_service.get_admin_role_ids(self.guild.id),
            ),
            view=AdminRolesView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )


class AdminRolesView(discord.ui.View):
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
        self.remove.disabled = not self.config_service.get_admin_role_ids(guild.id)

    @discord.ui.button(label="Adicionar", style=discord.ButtonStyle.success)
    async def add(
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

        await interaction.response.edit_message(
            embed=build_admin_roles_embed(
                self.guild,
                self.config_service.get_admin_role_ids(self.guild.id),
            ),
            view=AdminRoleAddView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )

    @discord.ui.button(label="Remover", style=discord.ButtonStyle.danger)
    async def remove(
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

        await interaction.response.edit_message(
            embed=build_admin_roles_embed(
                self.guild,
                self.config_service.get_admin_role_ids(self.guild.id),
            ),
            view=AdminRoleRemoveView(
                config_service=self.config_service,
                guild=self.guild,
                requester_id=self.requester_id,
            ),
        )


class ConfigGroup(app_commands.Group):
    def __init__(self, config_service: GuildConfigService) -> None:
        super().__init__(
            name="config",
            description="[ 🔐ADMIN ] Configurações de acesso do bot.",
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
            "Você não tem permissão para usar os comandos de configuração do bot.",
            ephemeral=True,
        )
        return False

    @app_commands.command(
        name="adm",
        description="[ 🔐ADMIN ] Gerencia os cargos que podem usar os comandos administrativos.",
    )
    async def adm(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        try:
            await interaction.response.send_message(
                embed=build_admin_roles_embed(
                    guild,
                    self.config_service.get_admin_role_ids(guild.id),
                ),
                view=AdminRolesView(
                    config_service=self.config_service,
                    guild=guild,
                    requester_id=interaction.user.id,
                ),
                ephemeral=True,
            )
        except Exception:
            LOGGER.exception(
                "Failed to open /config adm for guild=%s user=%s",
                guild.id,
                interaction.user.id,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Não consegui abrir o painel de configuração agora.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Não consegui abrir o painel de configuração agora.",
                    ephemeral=True,
                )

    @app_commands.command(
        name="buscar",
        description="[ 🔐ADMIN ] Adiciona ou remove um cargo com permissão de buscar jogos.",
    )
    @app_commands.describe(
        cargo="Cargo que vai ganhar ou perder permissão de busca",
        acao="Define se o cargo será adicionado ou removido",
    )
    @app_commands.choices(
        acao=[
            app_commands.Choice(name="adicionar", value="add"),
            app_commands.Choice(name="remover", value="remove"),
        ]
    )
    async def buscar(
        self,
        interaction: discord.Interaction,
        cargo: discord.Role,
        acao: app_commands.Choice[str] | None = None,
    ) -> None:
        guild = interaction.guild
        assert guild is not None

        try:
            selected_action = acao.value if acao is not None else "add"

            if selected_action == "add":
                self.config_service.add_search_role(guild.id, cargo.id)
                action_label = "adicionado"
            else:
                self.config_service.remove_search_role(guild.id, cargo.id)
                action_label = "removido"

            LOGGER.info(
                "Search role %s guild=%s role=%s user=%s",
                selected_action,
                guild.id,
                cargo.id,
                interaction.user.id,
            )

            role_ids = self.config_service.get_search_role_ids(guild.id)
            lines = []
            for role_id in role_ids:
                role = guild.get_role(role_id)
                if role is not None:
                    lines.append(f"- {role.mention}")

            role_list = "\n".join(lines) if lines else "- Nenhum cargo configurado"
            await interaction.response.send_message(
                f"Cargo {cargo.mention} {action_label} com sucesso.\n\n"
                f"Cargos que podem buscar jogos:\n{role_list}\n\n"
                "Se a lista ficar vazia, apenas o dono do servidor e os admins do bot poderão buscar.",
                ephemeral=True,
            )
        except Exception:
            LOGGER.exception(
                "Failed to update /config buscar for guild=%s role=%s user=%s",
                guild.id,
                cargo.id,
                interaction.user.id,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Não consegui atualizar a configuração de busca agora.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Não consegui atualizar a configuração de busca agora.",
                    ephemeral=True,
                )


    @app_commands.command(
        name="messages",
        description="[ 🔐ADMIN ] Edita as mensagens rotativas de atividade do bot.",
    )
    async def messages(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        await interaction.response.send_modal(
            ActivityMessagesModal(
                config_service=self.config_service,
                guild=guild,
            )
        )


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config_service: GuildConfigService) -> None:
        self.bot = bot
        self.config_service = config_service
        self.config_group = ConfigGroup(config_service)

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.config_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.config_group.name, type=self.config_group.type)


async def setup(bot: commands.Bot) -> None:
    config_service: GuildConfigService = bot.guild_config_service  # type: ignore[attr-defined]
    await bot.add_cog(ConfigCog(bot, config_service))
