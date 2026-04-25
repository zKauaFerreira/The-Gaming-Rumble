import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapper import OnlineFixScraper


MANUAL_CASES_PATH = ROOT / "tools" / "match_guard_cases.json"


LOOKUP_CASES = [
    ("Godfall", True),
    ("Demeo PC Edition", True),
    ("BROKE PROTOCOL Online City RPG", True),
    ("Hasbros BATTLESHIP", True),
    ("Lets Cook", True),
    ("Ghost of Tsushima DIRECTORS CUT", True),
    ("Teenage Mutant Ninja Turtles Shredders Revenge", True),
    ("No Mans Sky", True),
    ("Remnant II", True),
    ("Tiny Tinas Wonderlands", True),
    ("Project CARS 2", False),
    ("Project CARS", False),
    ("Age of Empires II", False),
    ("Resident Evil Resistance", False),
    ("Microsoft Flight Simulator", False),
    ("Halo Wars 2", False),
    ("Friday the 13th The Game", False),
    ("Spec Ops The Line", False),
    ("Grid 2", False),
    ("Horizon Chase 2", False),
    ("Project Arrhythmia", False),
    ("Galactic Civilizations IV", True),
    ("Titan Quest II", True),
    ("DARK SOULS III", True),
]


def load_manual_cases():
    if not MANUAL_CASES_PATH.exists():
        return {"positive": [], "negative": []}
    return json.loads(MANUAL_CASES_PATH.read_text(encoding="utf-8"))


def main():
    scraper = OnlineFixScraper()
    manual_cases = load_manual_cases()

    print("=== MODEL CASES ===")
    model_total = 0
    model_hits = 0
    hybrid_hits = 0
    for label in ("positive", "negative"):
        expected = label == "positive"
        for query, candidate in manual_cases.get(label, []):
            probability = scraper._guard_probability(query, candidate)
            canonical = scraper._is_canonical_steam_match(query, candidate)
            pure_predicted = probability >= 0.5
            hybrid_predicted = canonical or probability >= 0.5
            if pure_predicted == expected:
                model_hits += 1
            if hybrid_predicted == expected:
                hybrid_hits += 1
            model_total += 1
            print(
                f"{label.upper()} | p={probability:.4f} | canonical={int(canonical)} "
                f"| pure={int(pure_predicted)} | hybrid={int(hybrid_predicted)} | {query} -> {candidate}"
            )

    print("=== LOOKUP CASES ===")
    lookup_hits = 0
    for query, expected in LOOKUP_CASES:
        data, _ = scraper.get_steam_data(query)
        found = not data.get("not_found", False)
        if found == expected:
            lookup_hits += 1
        detail = data.get("steam_appid") if found else data.get("reason")
        print(f"LOOKUP | expected={int(expected)} | got={int(found)} | {query} | {detail}")

    print("=== SUMMARY ===")
    print(f"PURE_MODEL_ACCURACY={model_hits}/{model_total}")
    print(f"HYBRID_MODEL_ACCURACY={hybrid_hits}/{model_total}")
    print(f"LOOKUP_ACCURACY={lookup_hits}/{len(LOOKUP_CASES)}")


if __name__ == "__main__":
    main()
