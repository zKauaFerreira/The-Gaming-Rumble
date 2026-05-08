from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_GAMES_FILE = BASE_DIR / "online_fix_games.json"
DEFAULT_STATS_FILE = BASE_DIR / "stats.json"


def load_dotenv() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def download_to_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()

    with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as temp_file:
        temp_file.write(payload)
        temp_path = Path(temp_file.name)

    temp_path.replace(destination)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} não está configurado no .env.")
    return value


def main() -> None:
    load_dotenv()

    games_url = require_env("JSON_GAMES")
    stats_url = require_env("JSON_STATS")

    try:
        download_to_file(games_url, DEFAULT_GAMES_FILE)
        print(f"Arquivo atualizado: {DEFAULT_GAMES_FILE.name}")

        download_to_file(stats_url, DEFAULT_STATS_FILE)
        print(f"Arquivo atualizado: {DEFAULT_STATS_FILE.name}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha ao baixar arquivos: {exc}") from exc

    print("Sincronização concluída com sucesso.")


if __name__ == "__main__":
    main()
