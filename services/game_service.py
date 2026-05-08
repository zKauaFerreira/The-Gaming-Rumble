from __future__ import annotations

import random
from difflib import SequenceMatcher

from domain.models import GameDownload, SearchResult
from repositories.game_repository import GameRepository
from utils.text_utils import normalize_text


class GameService:
    def __init__(self, repository: GameRepository) -> None:
        self._repository = repository

    def search_games(self, query: str, limit: int = 5) -> list[SearchResult]:
        normalized_query = normalize_text(query)
        if not normalized_query:
            return []

        scored_results: list[SearchResult] = []
        for game in self._repository.list_games():
            title = normalize_text(game.title)
            if not title:
                continue

            score = self._score_match(normalized_query, title)
            if score < 0.35:
                continue

            scored_results.append(SearchResult(game=game, score=score))

        scored_results.sort(
            key=lambda item: (-item.score, len(item.game.title), item.game.title.casefold()),
        )
        return scored_results[:limit]

    def best_match(self, query: str) -> SearchResult | None:
        matches = self.search_games(query=query, limit=1)
        return matches[0] if matches else None

    def autocomplete_titles(self, query: str, limit: int = 25) -> list[str]:
        normalized_query = normalize_text(query)
        games = self._repository.list_games()

        if not normalized_query:
            titles = sorted(
                {
                    game.title
                    for game in games
                    if game.title.strip()
                }
            )
            return titles[:limit]

        ranked_titles: list[tuple[float, str]] = []
        for game in games:
            title = game.title.strip()
            normalized_title = normalize_text(title)
            if not title or not normalized_title:
                continue

            score = self._score_autocomplete_match(normalized_query, normalized_title)
            if score < 0.3:
                continue

            ranked_titles.append((score, title))

        ranked_titles.sort(key=lambda item: (-item[0], len(item[1]), item[1].casefold()))
        seen_titles: set[str] = set()
        titles: list[str] = []
        for _, title in ranked_titles:
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            titles.append(title)
            if len(titles) >= limit:
                break
        return titles[:limit]

    def random_game(self) -> SearchResult | None:
        games = [
            game
            for game in self._repository.list_games()
            if self._has_steam_metadata(game)
        ]
        if not games:
            return None
        return SearchResult(game=random.choice(games), score=1.0)

    def catalog_games(self) -> list[GameDownload]:
        games = [
            game
            for game in self._repository.list_games()
            if self._has_steam_metadata(game) and game.cover_url
        ]
        return sorted(games, key=lambda game: game.title.casefold())

    def stats_summary(self) -> str:
        stats = self._repository.get_stats()
        return (
            f"Catalogo declarado: {stats['declared_total']} | "
            f"registros carregados: {stats['loaded_total']}"
        )

    def reload(self) -> None:
        self._repository.clear_cache()

    @staticmethod
    def _score_match(query: str, title: str) -> float:
        if query == title:
            return 1.0
        if title.startswith(query):
            return 0.98
        if any(token.startswith(query) for token in title.split()):
            return 0.965
        if query in title:
            return 0.92

        query_tokens = query.split()
        title_tokens = title.split()
        token_hits = sum(1 for token in query_tokens if token in title_tokens)
        token_ratio = token_hits / max(len(query_tokens), 1)

        similarity = SequenceMatcher(None, query, title).ratio()
        partial_similarity = max(
            (SequenceMatcher(None, query, token).ratio() for token in title_tokens),
            default=0.0,
        )

        return max(similarity * 0.75 + token_ratio * 0.25, partial_similarity * 0.8)

    @staticmethod
    def _score_autocomplete_match(query: str, title: str) -> float:
        title_tokens = title.split()
        initials = "".join(token[0] for token in title_tokens if token)

        if query == title:
            return 1.0
        if title.startswith(query):
            return 0.995
        if any(token.startswith(query) for token in title_tokens):
            return 0.985
        if initials.startswith(query):
            return 0.975
        if f" {query}" in f" {title}":
            return 0.95
        if query in title:
            return 0.9

        similarity = SequenceMatcher(None, query, title).ratio()
        partial_similarity = max(
            (SequenceMatcher(None, query, token).ratio() for token in title_tokens),
            default=0.0,
        )
        initials_similarity = (
            SequenceMatcher(None, query, initials).ratio() if initials else 0.0
        )

        return max(
            similarity * 0.55 + partial_similarity * 0.25 + initials_similarity * 0.20,
            partial_similarity * 0.75,
        )

    @staticmethod
    def _has_steam_metadata(game: GameDownload) -> bool:
        steam_payload = game.raw.get("steam")
        if not isinstance(steam_payload, dict):
            return False
        if steam_payload.get("not_found") is True:
            return False
        return any(
            steam_payload.get(key)
            for key in (
                "steam_appid",
                "header_image",
                "short_description",
                "short_description_native",
                "pc_requirements",
                "controller_support",
            )
        )
