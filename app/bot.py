from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from app.config import Settings
from repositories.game_repository import GameRepository
from repositories.guild_config_repository import GuildConfigRepository
from repositories.stats_repository import StatsRepository
from services.game_service import GameService
from services.guild_config_service import GuildConfigService
from services.stats_service import StatsService

LOGGER = logging.getLogger(__name__)


@dataclass
class ActiveGameEphemeral:
    delete_callback: Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class FileSignature:
    exists: bool
    size: int
    mtime_ns: int


class RumbleBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.game_service = GameService(GameRepository(settings.data_file))
        self.guild_config_service = GuildConfigService(
            GuildConfigRepository(settings.config_file)
        )
        self.stats_service = StatsService(StatsRepository(settings.data_file.parent / "stats.json"))
        self._commands_synced = False
        self._sync_task: asyncio.Task[None] | None = None
        self._data_monitor_task: asyncio.Task[None] | None = None
        self._welcome_refresh_task: asyncio.Task[None] | None = None
        self._activity_rotation_task: asyncio.Task[None] | None = None
        self._initial_welcome_refresh_done = False
        self._synced_root_command_ids: dict[str, int] = {}
        self._active_game_ephemerals: dict[tuple[int, int], ActiveGameEphemeral] = {}
        self._last_presence_text: str | None = None
        self._watched_data_files = {
            settings.data_file.resolve(),
            (settings.data_file.parent / "stats.json").resolve(),
        }
        self._data_file_signatures = {
            path: self._build_file_signature(path)
            for path in self._watched_data_files
        }

    async def on_ready(self) -> None:
        user_tag = str(self.user) if self.user else "unknown-user"
        LOGGER.info("Bot connected as %s", user_tag)
        for guild in self.guilds:
            LOGGER.info("Connected guild: %s (%s)", guild.name, guild.id)

        if not self._commands_synced and self._sync_task is None:
            self._sync_task = self.loop.create_task(self._sync_commands())
        if self._data_monitor_task is None:
            self._data_monitor_task = self.loop.create_task(self._monitor_catalog_files())
        if not self._initial_welcome_refresh_done and self._welcome_refresh_task is None:
            self._welcome_refresh_task = self.loop.create_task(
                self._refresh_welcome_messages_on_startup()
            )
        if self._activity_rotation_task is None:
            self._activity_rotation_task = self.loop.create_task(
                self._rotate_presence_messages()
            )

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        LOGGER.exception("App command error: %s", error)
        if interaction.response.is_done():
            await interaction.followup.send(
                "Ocorreu um erro interno ao executar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Ocorreu um erro interno ao executar esse comando.",
            ephemeral=True,
        )

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.system")
        await self.load_extension("cogs.games")
        await self.load_extension("cogs.admin")
        await self.load_extension("cogs.config")
        await self.load_extension("cogs.bot_config")
        await self.load_extension("cogs.emoji")
        await self.load_extension("cogs.listener")

    async def _monitor_catalog_files(self) -> None:
        await self.wait_until_ready()
        LOGGER.info(
            "Catalog monitor ativo para: %s",
            ", ".join(str(path) for path in sorted(self._watched_data_files, key=str)),
        )
        while not self.is_closed():
            try:
                changed_files = self._poll_changed_data_files()
                if changed_files:
                    LOGGER.info(
                        "Mudança detectada nos arquivos do catálogo: %s",
                        ", ".join(path.name for path in changed_files),
                    )
                    self.game_service.reload()
                    self.stats_service.reload()
                    admin_cog = self.get_cog("AdminCog")
                    if admin_cog is not None and hasattr(admin_cog, "refresh_all_welcome_messages"):
                        refreshed = await admin_cog.refresh_all_welcome_messages()  # type: ignore[attr-defined]
                        LOGGER.info(
                            "Catalog data changed in %s. Welcome messages refreshed=%s",
                            ", ".join(path.name for path in changed_files),
                            refreshed,
                        )
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Failed while monitoring catalog data files")
                await asyncio.sleep(5)

    async def _refresh_welcome_messages_on_startup(self) -> None:
        await self.wait_until_ready()
        try:
            await asyncio.sleep(2)
            admin_cog = self.get_cog("AdminCog")
            if admin_cog is None or not hasattr(admin_cog, "refresh_all_welcome_messages"):
                LOGGER.info("Startup welcome refresh skipped: AdminCog indisponível")
                return

            refreshed = await admin_cog.refresh_all_welcome_messages()  # type: ignore[attr-defined]
            deleted_messages = 0
            if hasattr(admin_cog, "cleanup_configured_bot_channels"):
                deleted_messages = await admin_cog.cleanup_configured_bot_channels()  # type: ignore[attr-defined]
            self._initial_welcome_refresh_done = True
            LOGGER.info(
                "Startup welcome refresh concluído. Mensagens atualizadas=%s mensagens removidas=%s",
                refreshed,
                deleted_messages,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Failed to refresh welcome messages on startup")
        finally:
            self._welcome_refresh_task = None

    def _poll_changed_data_files(self) -> list[Path]:
        changed_files: list[Path] = []
        for path in self._watched_data_files:
            current_signature = self._build_file_signature(path)
            previous_signature = self._data_file_signatures.get(path)
            if previous_signature is None:
                self._data_file_signatures[path] = current_signature
                continue
            if current_signature != previous_signature:
                self._data_file_signatures[path] = current_signature
                changed_files.append(path)
        return changed_files

    @staticmethod
    def _build_file_signature(path: Path) -> FileSignature:
        if not path.exists():
            return FileSignature(exists=False, size=0, mtime_ns=0)

        stat = path.stat()
        return FileSignature(
            exists=True,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )

    def _game_ephemeral_key(
        self,
        guild_id: int | None,
        user_id: int,
    ) -> tuple[int, int]:
        return (guild_id or 0, user_id)

    async def clear_active_game_ephemeral(
        self,
        *,
        guild_id: int | None,
        user_id: int,
    ) -> None:
        key = self._game_ephemeral_key(guild_id, user_id)
        active = self._active_game_ephemerals.pop(key, None)
        if active is None:
            return

        try:
            await active.delete_callback()
            LOGGER.info(
                "Previous active game ephemeral cleared guild=%s user=%s",
                guild_id,
                user_id,
            )
        except (discord.NotFound, discord.HTTPException) as exc:
            LOGGER.warning(
                "Failed to clear previous active game ephemeral guild=%s user=%s error=%s",
                guild_id,
                user_id,
                exc,
            )

    def register_active_game_ephemeral(
        self,
        *,
        guild_id: int | None,
        user_id: int,
        delete_callback: Callable[[], Awaitable[None]],
    ) -> None:
        key = self._game_ephemeral_key(guild_id, user_id)
        self._active_game_ephemerals[key] = ActiveGameEphemeral(
            delete_callback=delete_callback,
        )

    async def refresh_rotating_activity(self) -> None:
        await self._apply_current_activity_message(force=True)

    async def _set_custom_presence(
        self,
        message: str | None,
        *,
        force: bool = False,
    ) -> None:
        normalized = message.strip() if isinstance(message, str) else None
        if not force and normalized == self._last_presence_text:
            return

        if normalized:
            await self.change_presence(activity=discord.CustomActivity(name=normalized))
        else:
            await self.change_presence(activity=None)

        self._last_presence_text = normalized

    def get_command_mention(self, qualified_name: str) -> str:
        root_name = qualified_name.split(" ", 1)[0].strip()
        command_id = self._synced_root_command_ids.get(root_name)
        if command_id is None:
            return f"/{qualified_name}"
        return f"</{qualified_name}:{command_id}>"

    async def resolve_command_mention(
        self,
        qualified_name: str,
        *,
        guild_id: int | None = None,
    ) -> str:
        root_name = qualified_name.split(" ", 1)[0].strip()
        command_id = self._synced_root_command_ids.get(root_name)
        if command_id is not None:
            return f"</{qualified_name}:{command_id}>"

        target_guild_id = guild_id or self.settings.guild_id
        if target_guild_id is not None:
            try:
                fetched_commands = await self.tree.fetch_commands(
                    guild=discord.Object(id=target_guild_id)
                )
                self._synced_root_command_ids.update(
                    {
                        command.name: command.id
                        for command in fetched_commands
                    }
                )
            except discord.HTTPException:
                LOGGER.warning(
                    "Failed to fetch guild commands for mention resolution guild=%s",
                    target_guild_id,
                )
        else:
            try:
                fetched_commands = await self.tree.fetch_commands()
                self._synced_root_command_ids.update(
                    {
                        command.name: command.id
                        for command in fetched_commands
                    }
                )
            except discord.HTTPException:
                LOGGER.warning("Failed to fetch global commands for mention resolution")

        command_id = self._synced_root_command_ids.get(root_name)
        if command_id is None:
            return f"/{qualified_name}"
        return f"</{qualified_name}:{command_id}>"

    async def _sync_commands(self) -> None:
        started_at = time.perf_counter()
        try:
            if self.settings.guild_id:
                guild = discord.Object(id=self.settings.guild_id)
                self.tree.copy_global_to(guild=guild)
                synced_commands = await self.tree.sync(guild=guild)
                self._synced_root_command_ids = {
                    command.name: command.id
                    for command in synced_commands
                }
                if not self.settings.sync_global_commands:
                    # In development we sync commands to a single guild for speed.
                    # If old global commands still exist remotely, Discord shows both
                    # the legacy global versions and the new guild-scoped ones.
                    # Clearing and syncing the global scope removes those duplicates.
                    self.tree.clear_commands(guild=None)
                    await self.tree.sync()
                    LOGGER.info(
                        "Legacy global commands cleared after guild sync in %.2fs",
                        time.perf_counter() - started_at,
                    )
                self._commands_synced = True
                LOGGER.info(
                    "Commands synced for guild %s in %.2fs",
                    self.settings.guild_id,
                    time.perf_counter() - started_at,
                )
                return

            if not self.settings.sync_global_commands:
                LOGGER.info(
                    "Skipping global command sync. Set DISCORD_GUILD_ID for fast dev sync "
                    "or SYNC_GLOBAL_COMMANDS=true to force global sync."
                )
                self._commands_synced = True
                return

            synced_commands = await self.tree.sync()
            self._synced_root_command_ids = {
                command.name: command.id
                for command in synced_commands
            }
            self._commands_synced = True
            LOGGER.info(
                "Global commands synced in %.2fs",
                time.perf_counter() - started_at,
            )
        finally:
            self._sync_task = None

    def _get_activity_source_messages(self) -> list[dict[str, int | str | None]]:
        for guild_id in self.guild_config_service.get_configured_guild_ids():
            items = self.guild_config_service.get_activity_messages(guild_id)
            if items:
                return items
        return []

    def _build_activity_placeholders(self) -> dict[str, str]:
        stats = self.stats_service.get_stats()
        latest_games = stats.latest_run_new_game_names if stats else []
        total_games = stats.total_games if stats else 0
        latest_update = self.stats_service.format_last_scrape_at(stats) if stats else None
        users_total = sum(guild.member_count or 0 for guild in self.guilds)
        latency_ms = round(self.latency * 1000)

        return {
            "{{total_games}}": f"{total_games:,}".replace(",", "."),
            "{{new_games_count}}": str(len(latest_games)),
            "{{latest_game}}": latest_games[0] if latest_games else "N/A",
            "{{latest_update}}": latest_update or "N/A",
            "{{servers}}": str(len(self.guilds)),
            "{{users}}": f"{users_total:,}".replace(",", "."),
            "{{latency_ms}}": str(latency_ms),
        }

    def _render_activity_message(self, template: str) -> str:
        rendered = template.strip()
        placeholders = self._build_activity_placeholders()
        for key, value in placeholders.items():
            rendered = rendered.replace(key, value)
        if len(rendered) > 128:
            LOGGER.warning(
                "Activity message excedeu 128 caracteres após renderização: %r",
                rendered,
            )
            return ""
        return rendered

    async def _apply_current_activity_message(self, *, force: bool = False) -> None:
        items = self._get_activity_source_messages()
        if not items:
            if force:
                await self._set_custom_presence(None, force=True)
            return

        first_message = self._render_activity_message(str(items[0].get("message", "")))
        if not first_message:
            return
        await self._set_custom_presence(first_message, force=force)

    async def _rotate_presence_messages(self) -> None:
        await self.wait_until_ready()
        index = 0
        last_signature: tuple[tuple[str, int | None], ...] = ()
        while not self.is_closed():
            try:
                items = self._get_activity_source_messages()
                signature = tuple(
                    (
                        str(item.get("message", "")).strip(),
                        int(item["duration_seconds"]) if item.get("duration_seconds") is not None else None,
                    )
                    for item in items
                    if str(item.get("message", "")).strip()
                )

                if not signature:
                    await self._set_custom_presence(None)
                    last_signature = ()
                    index = 0
                    await asyncio.sleep(5)
                    continue

                if signature != last_signature:
                    index = 0
                    last_signature = signature

                current_message, current_duration = signature[index]
                rendered_message = self._render_activity_message(current_message)
                if not rendered_message:
                    await asyncio.sleep(5)
                    continue

                await self._set_custom_presence(rendered_message)

                if len(signature) == 1:
                    await asyncio.sleep(30)
                    continue

                wait_seconds = current_duration or 15
                await asyncio.sleep(wait_seconds)
                index = (index + 1) % len(signature)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Failed while rotating presence messages")
                await asyncio.sleep(5)
