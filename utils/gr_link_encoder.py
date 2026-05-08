from __future__ import annotations

import base64
import json
import re
import zlib
from dataclasses import dataclass

from domain.models import GameDownload

DEFAULT_BANNER_URL = (
    "https://raw.githubusercontent.com/zKauaFerreira/"
    "The-Gaming-Rumble/main/public/logo.svg"
)
PART_FILE_PATTERN = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)
FIX_FILE_PATTERN = re.compile(r"(fix|repair)", re.IGNORECASE)


def _infer_parts_count(game: GameDownload) -> int:
    raw_files = game.raw.get("files", [])
    if not isinstance(raw_files, list):
        return 1

    detected_part_numbers: set[int] = set()
    fallback_archive_count = 0

    for item in raw_files:
        if not isinstance(item, dict):
            continue

        file_name = str(item.get("name", "")).strip()
        if not file_name:
            continue

        if FIX_FILE_PATTERN.search(file_name):
            continue

        match = PART_FILE_PATTERN.search(file_name)
        if match is not None:
            detected_part_numbers.add(int(match.group(1)))
            continue

        if file_name.lower().endswith((".rar", ".zip", ".7z")):
            fallback_archive_count += 1

    if detected_part_numbers:
        return max(detected_part_numbers)
    if fallback_archive_count > 0:
        return fallback_archive_count
    return 1


@dataclass(slots=True)
class GRLinkPayload:
    title: str
    banner: str
    parts: int
    fileSize: str
    magnet: str

    @classmethod
    def from_game(cls, game: GameDownload) -> "GRLinkPayload":
        return cls(
            title=game.title,
            banner=game.cover_url or DEFAULT_BANNER_URL,
            parts=_infer_parts_count(game),
            fileSize=game.file_size or "N/A",
            magnet=game.magnet or "",
        )

    def to_dict(self) -> dict[str, str | int]:
        return {
            "t": self.title,
            "b": self.banner,
            "p": self.parts,
            "s": self.fileSize,
            "m": self.magnet,
        }

    def encode(self) -> str:
        data = self.to_dict()
        json_str = json.dumps(data, ensure_ascii=False)
        compressed = zlib.compress(json_str.encode("utf-8"), level=9)
        b64 = base64.b64encode(compressed).decode("utf-8")
        url_safe = b64.replace("+", "-").replace("/", "_").replace("=", "")
        return url_safe

    def to_url(self, base_url: str = "https://gr-link.vercel.app") -> str:
        encoded = self.encode()
        return f"{base_url}/?data={encoded}"
