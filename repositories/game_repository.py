from __future__ import annotations

import json
from pathlib import Path

from domain.models import GameDownload


class GameRepository:
    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._cache: list[GameDownload] | None = None

    def _load_payload(self) -> dict:
        if not self._data_file.exists():
            raise FileNotFoundError(f"Data file not found: {self._data_file}")
        return json.loads(self._data_file.read_text(encoding="utf-8"))

    def list_games(self) -> list[GameDownload]:
        if self._cache is None:
            payload = self._load_payload()
            downloads = payload.get("downloads", [])
            self._cache = [GameDownload.from_dict(item) for item in downloads]
        return self._cache

    def get_stats(self) -> dict[str, int]:
        games = self.list_games()
        payload = self._load_payload()
        return {
            "declared_total": int(payload.get("total", 0)),
            "loaded_total": len(games),
        }

    def clear_cache(self) -> None:
        self._cache = None
