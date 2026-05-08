from app.config import DEFAULT_DATA_FILE
from repositories.game_repository import GameRepository
from services.game_service import GameService


def test_best_match_returns_result() -> None:
    service = GameService(GameRepository(DEFAULT_DATA_FILE))

    result = service.best_match("resident evil")

    assert result is not None
    assert "resident" in result.game.title.lower()
