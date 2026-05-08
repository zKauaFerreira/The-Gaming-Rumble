from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from app.bot import RumbleBot
from app.config import Settings
from app.logging_config import configure_logging


WATCH_SUFFIXES = {".py", ".json", ".env", ".toml"}
WATCH_ROOTS = ("app", "cogs", "domain", "repositories", "services", "utils", "tests")
WATCH_FILES = ("main.py", ".env", ".env.example", "requirements.txt", "requirements_translations.json")
IGNORE_FILES = {"config.json", "online_fix_games.json", "stats.json"}
IGNORE_DIRS = {"__pycache__", ".git", ".venv", "venv"}
CHILD_FLAG = "RUMBLE_BOT_CHILD"


def _iter_watch_files(base_dir: Path) -> list[Path]:
    files: list[Path] = []

    for name in WATCH_FILES:
        path = base_dir / name
        if path.exists() and path.is_file():
            files.append(path)

    for root_name in WATCH_ROOTS:
        root = base_dir / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            if path.name in IGNORE_FILES:
                continue
            if path.suffix in WATCH_SUFFIXES:
                files.append(path)

    unique_files = sorted({path.resolve() for path in files})
    return unique_files


def _snapshot(base_dir: Path) -> dict[Path, float]:
    snapshot: dict[Path, float] = {}
    for path in _iter_watch_files(base_dir):
        try:
            snapshot[path] = path.stat().st_mtime
        except FileNotFoundError:
            continue
    return snapshot


def _diff_snapshots(previous: dict[Path, float], current: dict[Path, float]) -> list[str]:
    changed: list[str] = []
    for path, mtime in current.items():
        if previous.get(path) != mtime:
            changed.append(path.name)
    for path in previous:
        if path not in current:
            changed.append(path.name)
    return sorted(set(changed))


def _clear_console() -> None:
    if not sys.stdout.isatty():
        return
    if os.name != "nt" and not os.getenv("TERM"):
        return
    os.system("cls" if os.name == "nt" else "clear")


def _format_change_list(changed_files: list[str]) -> str:
    if not changed_files:
        return "Mudancas detectadas, reiniciando..."
    return f"Mudancas nos arquivos: {', '.join(changed_files)}. Reiniciando..."


def _run_bot() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN is not configured.")

    bot = RumbleBot(settings)
    bot.run(settings.discord_token)


def _supervise() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    base_dir = Path(__file__).resolve().parent
    env = os.environ.copy()
    env[CHILD_FLAG] = "1"

    snapshot = _snapshot(base_dir)

    while True:
        _clear_console()
        print("Rumble Bot dev supervisor iniciado.")
        print("Autoreload ativo. Monitorando arquivos do projeto...\n")

        child = subprocess.Popen([sys.executable, str(base_dir / "main.py")], env=env)

        try:
            while True:
                time.sleep(settings.dev_reload_interval)
                current_snapshot = _snapshot(base_dir)
                changed_files = _diff_snapshots(snapshot, current_snapshot)

                if changed_files:
                    print(_format_change_list(changed_files))
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    snapshot = current_snapshot
                    break

                if child.poll() is not None:
                    print(f"Processo do bot finalizado com codigo {child.returncode}. Reiniciando...")
                    snapshot = current_snapshot
                    time.sleep(1)
                    break
        except KeyboardInterrupt:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            raise


def main() -> None:
    if os.getenv(CHILD_FLAG) == "1":
        _run_bot()
        return

    settings = Settings.from_env()
    if settings.dev_autoreload:
        _supervise()
        return

    _run_bot()


if __name__ == "__main__":
    main()
