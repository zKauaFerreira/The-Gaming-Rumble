from __future__ import annotations

import discord

from repositories.guild_config_repository import GuildConfigRepository


class GuildConfigService:
    def __init__(self, repository: GuildConfigRepository) -> None:
        self._repository = repository

    def get_bot_channel_id(self, guild_id: int) -> int | None:
        return self._repository.get_channel_id(guild_id)

    def set_bot_channel_id(self, guild_id: int, channel_id: int) -> None:
        self._repository.set_channel_id(guild_id, channel_id)

    def get_welcome_message_id(self, guild_id: int) -> int | None:
        return self._repository.get_welcome_message_id(guild_id)

    def set_welcome_message_id(self, guild_id: int, message_id: int | None) -> None:
        self._repository.set_welcome_message_id(guild_id, message_id)

    def get_admin_role_ids(self, guild_id: int) -> list[int]:
        return self._repository.get_admin_role_ids(guild_id)

    def add_admin_role(self, guild_id: int, role_id: int) -> None:
        role_ids = self.get_admin_role_ids(guild_id)
        if role_id not in role_ids:
            role_ids.append(role_id)
        self._repository.set_admin_role_ids(guild_id, role_ids)

    def remove_admin_role(self, guild_id: int, role_id: int) -> None:
        role_ids = [item for item in self.get_admin_role_ids(guild_id) if item != role_id]
        self._repository.set_admin_role_ids(guild_id, role_ids)

    def get_search_role_ids(self, guild_id: int) -> list[int]:
        return self._repository.get_search_role_ids(guild_id)

    def add_search_role(self, guild_id: int, role_id: int) -> None:
        role_ids = self.get_search_role_ids(guild_id)
        if role_id not in role_ids:
            role_ids.append(role_id)
        self._repository.set_search_role_ids(guild_id, role_ids)

    def remove_search_role(self, guild_id: int, role_id: int) -> None:
        role_ids = [item for item in self.get_search_role_ids(guild_id) if item != role_id]
        self._repository.set_search_role_ids(guild_id, role_ids)

    def get_delete_notice_after_seconds(self, guild_id: int) -> int:
        return self._repository.get_delete_notice_after_seconds(guild_id)

    def set_delete_notice_after_seconds(self, guild_id: int, seconds: int) -> None:
        self._repository.set_delete_notice_after_seconds(guild_id, seconds)

    def get_ephemeral_game_result_seconds(self, guild_id: int) -> int:
        return self._repository.get_ephemeral_game_result_seconds(guild_id)

    def set_ephemeral_game_result_seconds(self, guild_id: int, seconds: int) -> None:
        self._repository.set_ephemeral_game_result_seconds(guild_id, seconds)

    def get_panel_role_id(self, guild_id: int) -> int | None:
        return self._repository.get_panel_role_id(guild_id)

    def set_panel_role_id(self, guild_id: int, role_id: int | None) -> None:
        self._repository.set_panel_role_id(guild_id, role_id)

    def get_share_role_id(self, guild_id: int) -> int | None:
        return self._repository.get_share_role_id(guild_id)

    def set_share_role_id(self, guild_id: int, role_id: int | None) -> None:
        self._repository.set_share_role_id(guild_id, role_id)

    def get_activity_messages(self, guild_id: int) -> list[dict[str, int | str | None]]:
        return self._repository.get_activity_messages(guild_id)

    def set_activity_messages(
        self,
        guild_id: int,
        items: list[dict[str, int | str | None]],
    ) -> None:
        self._repository.set_activity_messages(guild_id, items)

    def get_ui_emojis(self, guild_id: int) -> dict[str, str]:
        return self._repository.get_ui_emojis(guild_id)

    def get_ui_emoji(self, guild_id: int, key: str) -> str | None:
        return self.get_ui_emojis(guild_id).get(key)

    def set_ui_emoji(self, guild_id: int, key: str, emoji_value: str) -> None:
        emojis = self.get_ui_emojis(guild_id)
        emojis[key] = emoji_value
        self._repository.set_ui_emojis(guild_id, emojis)

    def remove_ui_emoji(self, guild_id: int, key: str) -> None:
        emojis = self.get_ui_emojis(guild_id)
        emojis.pop(key, None)
        self._repository.set_ui_emojis(guild_id, emojis)

    def get_configured_guild_ids(self) -> list[int]:
        return self._repository.get_configured_guild_ids()

    def can_manage(self, guild: discord.Guild, member: discord.abc.User | discord.Member) -> bool:
        if guild.owner_id == member.id:
            return True
        if not isinstance(member, discord.Member):
            return False

        allowed_role_ids = self.get_admin_role_ids(guild.id)
        if not allowed_role_ids:
            return False

        member_role_ids = {role.id for role in member.roles}
        return any(role_id in member_role_ids for role_id in allowed_role_ids)

    def can_search(self, guild: discord.Guild, member: discord.abc.User | discord.Member) -> bool:
        if guild.owner_id == member.id:
            return True
        if not isinstance(member, discord.Member):
            return False
        if self.can_manage(guild, member):
            return True

        allowed_role_ids = self.get_search_role_ids(guild.id)
        if not allowed_role_ids:
            return False

        member_role_ids = {role.id for role in member.roles}
        return any(role_id in member_role_ids for role_id in allowed_role_ids)

    def can_share_game(self, guild: discord.Guild, member: discord.abc.User | discord.Member) -> bool:
        if guild.owner_id == member.id:
            return True
        if not isinstance(member, discord.Member):
            return False
        if self.can_manage(guild, member):
            return True

        share_role_id = self.get_share_role_id(guild.id)
        if share_role_id is None:
            return False

        member_role_ids = {role.id for role in member.roles}
        return share_role_id in member_role_ids
