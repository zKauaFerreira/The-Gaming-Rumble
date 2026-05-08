from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from domain.models import CatalogStats
from repositories.stats_repository import StatsRepository

SAO_PAULO_TZ = timezone(timedelta(hours=-3))


class StatsService:
    def __init__(self, repository: StatsRepository) -> None:
        self._repository = repository

    def get_stats(self) -> CatalogStats | None:
        return self._repository.get_stats()

    def reload(self) -> None:
        self._repository.clear_cache()

    @staticmethod
    def get_last_scrape_datetime(stats: CatalogStats | None) -> datetime | None:
        if stats is None or stats.last_scrape_at is None:
            return None
        return stats.last_scrape_at.replace(tzinfo=SAO_PAULO_TZ)

    @classmethod
    def format_last_scrape_at(cls, stats: CatalogStats | None) -> str | None:
        last_scrape_at = cls.get_last_scrape_datetime(stats)
        if last_scrape_at is None:
            return None
        return last_scrape_at.strftime("%d/%m/%Y às %H:%M")

    @classmethod
    def get_last_scrape_unix(cls, stats: CatalogStats | None) -> int | None:
        last_scrape_at = cls.get_last_scrape_datetime(stats)
        if last_scrape_at is None:
            return None
        return int(last_scrape_at.astimezone(UTC).timestamp())
