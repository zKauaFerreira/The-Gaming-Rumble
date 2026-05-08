from __future__ import annotations

import json
from pathlib import Path

from domain.models import CatalogStats


class StatsRepository:
    def __init__(self, stats_file: Path) -> None:
        self._stats_file = stats_file
        self._cache: CatalogStats | None = None

    def get_stats(self) -> CatalogStats | None:
        if not self._stats_file.exists():
            return None

        if self._cache is None:
            payload = json.loads(self._stats_file.read_text(encoding="utf-8"))
            self._cache = CatalogStats.from_dict(payload)
        return self._cache

    def clear_cache(self) -> None:
        self._cache = None
