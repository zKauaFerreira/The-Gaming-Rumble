from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_FILE = BASE_DIR / "online_fix_games.json"
DEFAULT_CONFIG_FILE = BASE_DIR / "config.json"


def _load_dotenv() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


@dataclass(slots=True)
class Settings:
    discord_token: str
    log_level: str
    data_file: Path
    config_file: Path
    sync_global_commands: bool
    dev_autoreload: bool
    dev_reload_interval: float
    guild_id: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()

        guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
        data_file_raw = os.getenv("DATA_FILE", "").strip()
        config_file_raw = os.getenv("CONFIG_FILE", "").strip()
        sync_global_commands_raw = os.getenv("SYNC_GLOBAL_COMMANDS", "false").strip().casefold()
        dev_autoreload_raw = os.getenv("DEV_AUTORELOAD", "true").strip().casefold()
        dev_reload_interval_raw = os.getenv("DEV_RELOAD_INTERVAL", "1.0").strip()

        return cls(
            discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            data_file=Path(data_file_raw) if data_file_raw else DEFAULT_DATA_FILE,
            config_file=(
                Path(config_file_raw)
                if config_file_raw
                else DEFAULT_CONFIG_FILE
            ),
            sync_global_commands=sync_global_commands_raw in {"1", "true", "yes", "on"},
            dev_autoreload=dev_autoreload_raw in {"1", "true", "yes", "on"},
            dev_reload_interval=float(dev_reload_interval_raw or "1.0"),
            guild_id=int(guild_id_raw) if guild_id_raw else None,
        )
