from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GameDownload:
    title: str
    url: str
    page: int | None = None
    file_size: str | None = None
    torrent_file: str | None = None
    magnet: str | None = None
    last_update: str | None = None
    release_date: str | None = None
    steam_appid: int | None = None
    cover_url: str | None = None
    description: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GameDownload":
        steam = payload.get("steam") or {}
        return cls(
            title=str(payload.get("title", "")).strip(),
            url=str(payload.get("url", "")).strip(),
            page=payload.get("page"),
            file_size=payload.get("fileSize"),
            torrent_file=payload.get("torrent_file"),
            magnet=payload.get("magnet"),
            last_update=payload.get("last_update"),
            release_date=payload.get("release_date"),
            steam_appid=steam.get("steam_appid"),
            cover_url=steam.get("header_image"),
            description=steam.get("short_description")
            or steam.get("short_description_native"),
            raw=payload,
        )


@dataclass(slots=True)
class SearchResult:
    game: GameDownload
    score: float


@dataclass(slots=True)
class CatalogStats:
    total_games: int
    latest_run_new_game_names: list[str]
    last_scrape_at: datetime | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CatalogStats":
        raw_last_scrape_at = str(payload.get("last_scrape_at", "")).strip()
        last_scrape_at: datetime | None = None
        if raw_last_scrape_at:
            try:
                last_scrape_at = datetime.strptime(raw_last_scrape_at, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last_scrape_at = None

        latest_names = payload.get("latest_run_new_game_names", [])
        if not isinstance(latest_names, list):
            latest_names = []

        return cls(
            total_games=int(payload.get("total_games", 0) or 0),
            latest_run_new_game_names=[
                str(item).strip()
                for item in latest_names
                if str(item).strip()
            ],
            last_scrape_at=last_scrape_at,
        )
