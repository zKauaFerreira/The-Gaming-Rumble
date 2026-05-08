from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GuildConfigRepository:
    def __init__(self, config_file: Path) -> None:
        self._config_file = config_file
        if not self._config_file.exists():
            self._config_file.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        return json.loads(self._config_file.read_text(encoding="utf-8"))

    def _save(self, payload: dict[str, Any]) -> None:
        self._config_file.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _ensure_guild_config(self, payload: dict[str, Any], guild_id: int) -> dict[str, Any]:
        guild_key = str(guild_id)
        guild_config = payload.get(guild_key)
        if not isinstance(guild_config, dict):
            guild_config = {}

        guild_config.setdefault("channel_id", None)
        guild_config.setdefault("welcome_message_id", None)
        guild_config.setdefault("admin_role_ids", [])
        guild_config.setdefault("search_role_ids", [])
        guild_config.setdefault("delete_notice_after_seconds", 5)
        guild_config.setdefault("ephemeral_game_result_seconds", 15)
        guild_config.setdefault("panel_role_id", None)
        guild_config.setdefault("share_role_id", None)
        guild_config.setdefault("activity_messages", [])
        guild_config.setdefault("ui_emojis", {})
        payload[guild_key] = guild_config
        return guild_config

    def get_guild_config(self, guild_id: int) -> dict[str, Any]:
        payload = self._load()
        original_payload = json.dumps(payload, sort_keys=True)
        guild_config = self._ensure_guild_config(payload, guild_id)
        if json.dumps(payload, sort_keys=True) != original_payload:
            self._save(payload)
        return guild_config

    def get_channel_id(self, guild_id: int) -> int | None:
        guild_config = self.get_guild_config(guild_id)
        channel_id = guild_config.get("channel_id")
        return int(channel_id) if channel_id else None

    def set_channel_id(self, guild_id: int, channel_id: int) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["channel_id"] = channel_id
        self._save(payload)

    def get_welcome_message_id(self, guild_id: int) -> int | None:
        guild_config = self.get_guild_config(guild_id)
        message_id = guild_config.get("welcome_message_id")
        return int(message_id) if message_id else None

    def set_welcome_message_id(self, guild_id: int, message_id: int | None) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["welcome_message_id"] = message_id
        self._save(payload)

    def get_admin_role_ids(self, guild_id: int) -> list[int]:
        guild_config = self.get_guild_config(guild_id)
        role_ids = guild_config.get("admin_role_ids", [])
        return [int(role_id) for role_id in role_ids]

    def set_admin_role_ids(self, guild_id: int, role_ids: list[int]) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["admin_role_ids"] = sorted(set(int(role_id) for role_id in role_ids))
        self._save(payload)

    def get_search_role_ids(self, guild_id: int) -> list[int]:
        guild_config = self.get_guild_config(guild_id)
        role_ids = guild_config.get("search_role_ids", [])
        return [int(role_id) for role_id in role_ids]

    def set_search_role_ids(self, guild_id: int, role_ids: list[int]) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["search_role_ids"] = sorted(set(int(role_id) for role_id in role_ids))
        self._save(payload)

    def get_delete_notice_after_seconds(self, guild_id: int) -> int:
        guild_config = self.get_guild_config(guild_id)
        seconds = guild_config.get("delete_notice_after_seconds", 5)
        return int(seconds)

    def set_delete_notice_after_seconds(self, guild_id: int, seconds: int) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["delete_notice_after_seconds"] = int(seconds)
        self._save(payload)

    def get_ephemeral_game_result_seconds(self, guild_id: int) -> int:
        guild_config = self.get_guild_config(guild_id)
        seconds = guild_config.get("ephemeral_game_result_seconds", 15)
        return int(seconds)

    def set_ephemeral_game_result_seconds(self, guild_id: int, seconds: int) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["ephemeral_game_result_seconds"] = int(seconds)
        self._save(payload)

    def get_panel_role_id(self, guild_id: int) -> int | None:
        guild_config = self.get_guild_config(guild_id)
        role_id = guild_config.get("panel_role_id")
        return int(role_id) if role_id else None

    def set_panel_role_id(self, guild_id: int, role_id: int | None) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["panel_role_id"] = int(role_id) if role_id else None
        self._save(payload)

    def get_share_role_id(self, guild_id: int) -> int | None:
        guild_config = self.get_guild_config(guild_id)
        role_id = guild_config.get("share_role_id")
        return int(role_id) if role_id else None

    def set_share_role_id(self, guild_id: int, role_id: int | None) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["share_role_id"] = int(role_id) if role_id else None
        self._save(payload)

    def get_activity_messages(self, guild_id: int) -> list[dict[str, Any]]:
        guild_config = self.get_guild_config(guild_id)
        raw_items = guild_config.get("activity_messages", [])
        if not isinstance(raw_items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            message = str(item.get("message", "")).strip()
            if not message:
                continue
            duration_seconds = item.get("duration_seconds")
            normalized.append(
                {
                    "message": message,
                    "duration_seconds": int(duration_seconds) if duration_seconds is not None else None,
                }
            )
        return normalized

    def set_activity_messages(self, guild_id: int, items: list[dict[str, Any]]) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["activity_messages"] = [
            {
                "message": str(item["message"]).strip(),
                "duration_seconds": (
                    int(item["duration_seconds"])
                    if item.get("duration_seconds") is not None
                    else None
                ),
            }
            for item in items
            if str(item.get("message", "")).strip()
        ]
        self._save(payload)

    def get_ui_emojis(self, guild_id: int) -> dict[str, str]:
        guild_config = self.get_guild_config(guild_id)
        payload = guild_config.get("ui_emojis")
        if payload is None:
            payload = guild_config.get("ui_emoji_ids", {})
        if not isinstance(payload, dict):
            return {}
        normalized: dict[str, str] = {}
        for key, value in payload.items():
            if isinstance(value, int):
                normalized[str(key)] = f"id:{value}"
            elif isinstance(value, str) and value.strip():
                normalized[str(key)] = value.strip()
        return normalized

    def set_ui_emojis(self, guild_id: int, emojis: dict[str, str]) -> None:
        payload = self._load()
        guild_config = self._ensure_guild_config(payload, guild_id)
        guild_config["ui_emojis"] = {
            str(key): str(value)
            for key, value in emojis.items()
            if str(value).strip()
        }
        guild_config.pop("ui_emoji_ids", None)
        self._save(payload)

    def get_configured_guild_ids(self) -> list[int]:
        payload = self._load()
        configured_ids: list[int] = []
        for raw_key, raw_value in payload.items():
            if not isinstance(raw_value, dict):
                continue
            try:
                configured_ids.append(int(raw_key))
            except ValueError:
                continue
        return configured_ids
