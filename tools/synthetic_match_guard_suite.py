import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapper import OnlineFixScraper


CASES_PATH = ROOT / "tools" / "match_guard_synthetic_cases.json"


def local_pick(scraper, query):
    alias_candidate = scraper._resolve_alias_candidate(query)
    if alias_candidate:
        return alias_candidate
    candidates = scraper._search_in_catalog(scraper._normalize(query), query)
    if not candidates:
        return None
    return scraper._pick_guarded_candidate(query, candidates)


def main():
    scraper = OnlineFixScraper()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    hits = 0
    for case in cases:
        query = case["query"]
        expected_found = case["expected_found"]
        picked = local_pick(scraper, query)
        found = picked is not None
        ok = found == expected_found
        hits += int(ok)
        got = picked["name"] if picked else "NONE"
        print(
            f"SYN | ok={int(ok)} | expected={int(expected_found)} | got={int(found)} "
            f"| {case['category']} | {json.dumps(query, ensure_ascii=True)} | {json.dumps(got, ensure_ascii=True)}"
        )

    print("=== SUMMARY ===")
    print(f"SYNTHETIC_LOOKUP_ACCURACY={hits}/{len(cases)}")


if __name__ == "__main__":
    main()
