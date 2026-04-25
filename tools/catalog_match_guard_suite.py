import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapper import OnlineFixScraper
from tools.match_guard_catalog_cases import (
    catalog_pattern_stats,
    dump_cases_preview,
    generate_catalog_edge_negative_examples,
    generate_catalog_edge_positive_examples,
)


def load_apps():
    path = ROOT / "steam_applist_full.json"
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)["apps"]


def local_pick(scraper, query):
    alias_candidate = scraper._resolve_alias_candidate(query)
    if alias_candidate:
        return alias_candidate
    candidates = scraper._search_in_catalog(scraper._normalize(query), query)
    if not candidates:
        return None
    return scraper._pick_guarded_candidate(query, candidates)


def main():
    apps = load_apps()
    scraper = OnlineFixScraper()

    positive_cases = generate_catalog_edge_positive_examples(apps, per_category=35)
    negative_cases = generate_catalog_edge_negative_examples(apps, family_limit=80)

    print("=== CATALOG PATTERN STATS ===")
    for key, value in sorted(catalog_pattern_stats(apps).items()):
        print(f"{key}={value}")

    print("=== POSITIVE CASE PREVIEW ===")
    print(dump_cases_preview(positive_cases, limit=10))

    print("=== NEGATIVE CASE PREVIEW ===")
    print(dump_cases_preview(negative_cases, limit=10))

    print("=== POSITIVE CATALOG SUITE ===")
    positive_by_category = defaultdict(lambda: [0, 0])
    total_positive_hits = 0
    for case in positive_cases:
        picked = local_pick(scraper, case["query"])
        ok = bool(picked) and picked["id"] == case["appid"]
        positive_by_category[case["category"]][0] += int(ok)
        positive_by_category[case["category"]][1] += 1
        total_positive_hits += int(ok)
        print(
            f"POS | {case['category']} | ok={int(ok)} | query={json.dumps(case['query'], ensure_ascii=True)} "
            f"| expected={case['appid']} | got={(picked['id'] if picked else 'NONE')}"
        )

    print("=== NEGATIVE CATALOG SUITE ===")
    negative_hits = 0
    for case in negative_cases:
        restricted_pick = scraper._pick_guarded_candidate(case["query"], [{
            "id": case["wrong_appid"],
            "name": case["candidate"],
            "score": 100,
        }])
        conflict = scraper._guard_sequence_conflict(case["query"], case["candidate"])
        ok = conflict and restricted_pick is None
        negative_hits += int(ok)
        print(
            f"NEG | {case['category']} | ok={int(ok)} | conflict={int(conflict)} "
            f"| query={json.dumps(case['query'], ensure_ascii=True)} "
            f"| wrong={json.dumps(case['candidate'], ensure_ascii=True)}"
        )

    print("=== SUMMARY ===")
    for category, (hits, total) in sorted(positive_by_category.items()):
        print(f"CATEGORY_{category.upper()}={hits}/{total}")
    print(f"CATALOG_POSITIVE_ACCURACY={total_positive_hits}/{len(positive_cases)}")
    print(f"CATALOG_NEGATIVE_ACCURACY={negative_hits}/{len(negative_cases)}")


if __name__ == "__main__":
    main()
