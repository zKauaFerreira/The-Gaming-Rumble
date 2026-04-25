import json
import math
import argparse
import random
import re
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz
from match_guard_catalog_cases import (
    generate_catalog_edge_negative_examples,
    generate_catalog_edge_positive_examples,
)


ROOT = Path(__file__).resolve().parents[1]
ONLINE_FIX_PATH = ROOT / "online_fix_games.json"
STEAM_CATALOG_PATH = ROOT / "steam_applist_full.json"
MANUAL_CASES_PATH = ROOT / "tools" / "match_guard_cases.json"
MODEL_OUTPUT_PATH = ROOT / "tools" / "match_guard_model.json"


COMMON_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "may", "might", "must", "can", "edition", "game", "games",
    "vr", "online", "simulator", "digital", "collection", "ultimate",
    "definitive", "complete", "remastered", "remaster", "enhanced",
    "director", "directors", "cut", "beta", "alpha", "demo", "pc"
}

DESCRIPTOR_WORDS = {
    "edition", "editions", "game", "games", "vr", "online", "simulator", "digital",
    "collection", "ultimate", "definitive", "complete", "remastered", "remaster",
    "enhanced", "director", "directors", "cut", "beta", "alpha", "demo", "pc",
    "hd", "bundle", "pack", "deluxe", "anniversary", "redux", "reloaded",
    "multiplayer", "coop", "co", "op", "goty", "city", "rpg", "mode", "version",
    "launch", "steam", "store", "full", "s"
}

ROMAN_VALUES = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
    "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
    "xvi": 16
}

TRAILING_DESCRIPTOR_PATTERNS = [
    r"\s+ultimate edition$",
    r"\s+definitive edition$",
    r"\s+complete edition$",
    r"\s+digital edition$",
    r"\s+enhanced edition$",
    r"\s+anniversary edition$",
    r"\s+legacy collection$",
    r"\s+classic collection$",
    r"\s+director'?s cut$",
    r"\s+directors cut$",
    r"\s+pc edition$",
    r"\s+hd remaster$",
    r"\s+remaster(?:ed)?$",
    r"\s+redux$",
    r"\s+reloaded$",
    r"\s+ultimate$",
    r"\s+definitive$",
    r"\s+enhanced$",
]


def normalize(text):
    text = text or ""
    text = text.lower()
    text = text.replace("’", "").replace("'", "").replace("`", "")
    text = text.replace("™", " ").replace("®", " ").replace("©", " ")
    text = re.sub(r"[':!?,.%&()+\\[\\]{}|/\\\\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def textual_tokens(text):
    return re.findall(r"[a-z0-9]+", normalize(text))


def meaningful_tokens(text):
    return [tok for tok in textual_tokens(text) if len(tok) >= 2 and tok not in COMMON_WORDS]


def distinctive_tokens(text):
    return [tok for tok in meaningful_tokens(text) if len(tok) >= 4]


def extract_numbers(text):
    numbers = [int(x) for x in re.findall(r"\b\d{1,4}\b", text or "")]
    roman = [ROMAN_VALUES[tok] for tok in textual_tokens(text) if tok in ROMAN_VALUES]
    return sorted(set(numbers + roman))


def extract_year(text):
    years = [int(x) for x in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")]
    return years[0] if years else None


def stem_token(token):
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token == "bros":
        return "bro"
    if token.endswith("s") and len(token) > 3 and not token.endswith(("ss", "us", "is", "os")):
        return token[:-1]
    return token


def canonical_tokens(text, drop_descriptors=False):
    roman_tokens = set(ROMAN_VALUES)
    tokens = []
    for token in textual_tokens(text):
        if token in COMMON_WORDS:
            continue
        if drop_descriptors and token in DESCRIPTOR_WORDS:
            continue
        token = stem_token(token)
        if len(token) < 2 and not token.isdigit() and token not in roman_tokens:
            continue
        tokens.append(token)
    return tokens


def canonical_text(text, drop_descriptors=False):
    return " ".join(canonical_tokens(text, drop_descriptors=drop_descriptors))


def remove_trailing_descriptors(text):
    reduced = normalize(text)
    changed = True
    while changed and reduced:
        changed = False
        for pattern in TRAILING_DESCRIPTOR_PATTERNS:
            updated = re.sub(pattern, "", reduced).strip()
            if updated != reduced:
                reduced = updated
                changed = True
    return reduced


def descriptor_stripped_match(query, candidate):
    q_stripped = remove_trailing_descriptors(query)
    c_stripped = remove_trailing_descriptors(candidate)
    return (
        bool(q_stripped)
        and bool(c_stripped)
        and (
            q_stripped == c_stripped
            or q_stripped == normalize(candidate)
            or c_stripped == normalize(query)
        )
    )


def synthetic_query_variants(name):
    variants = set()
    clean = normalize(name)
    if not clean:
        return variants

    variants.add(clean)
    variants.add(re.sub(r"\s+", " ", clean.replace("&", " and ")).strip())
    variants.add(re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", clean)).strip())

    stripped = remove_trailing_descriptors(name)
    if stripped and stripped != clean:
        variants.add(stripped)
        variants.add(f"{stripped} pc edition")
        variants.add(f"{stripped} digital edition")
        variants.add(f"{stripped} ultimate edition")
        variants.add(f"{stripped} definitive edition")

    ordinal_edition_variant = re.sub(r"\s+\d+(st|nd|rd|th)\s+edition$", " edition", clean).strip()
    if ordinal_edition_variant and ordinal_edition_variant != clean:
        variants.add(ordinal_edition_variant)

    if ":" in name:
        variants.add(normalize(name.replace(":", " ")))
        variants.add(normalize(name.split(":", 1)[0]))

    if "'" in name:
        variants.add(normalize(name.replace("'", "")))
        variants.add(normalize(re.sub(r"'s\b", "s", name)))

    if "’" in name:
        variants.add(normalize(name.replace("’", "")))
        variants.add(normalize(re.sub(r"’s\b", "s", name)))

    core = canonical_text(name, drop_descriptors=True)
    if core and core == canonical_text(name, drop_descriptors=False):
        variants.add(f"{clean} pc edition")
        variants.add(f"{clean} online")
        variants.add(f"{clean} digital edition")

    return {variant for variant in variants if variant and variant != clean}


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def overlap_fraction(source, target):
    s, t = set(source), set(target)
    if not s:
        return 1.0
    return len(s & t) / len(s)


def franchise_key(text):
    core = canonical_tokens(text, drop_descriptors=True)
    key_tokens = []
    for token in core:
        if token.isdigit() or token in ROMAN_VALUES:
            continue
        key_tokens.append(token)
        if len(key_tokens) >= 2:
            break
    return " ".join(key_tokens)


def sequence_conflict(query, candidate):
    q_numbers = extract_numbers(query)
    c_numbers = extract_numbers(candidate)
    if not q_numbers or not c_numbers:
        return False
    if franchise_key(query) and franchise_key(query) == franchise_key(candidate) and q_numbers != c_numbers:
        return True
    return False


def feature_vector(query, candidate):
    q_norm = normalize(query)
    c_norm = normalize(candidate)
    q_tokens = textual_tokens(query)
    c_tokens = textual_tokens(candidate)
    q_meaning = meaningful_tokens(query)
    c_meaning = meaningful_tokens(candidate)
    q_dist = distinctive_tokens(query)
    c_dist = distinctive_tokens(candidate)
    q_numbers = extract_numbers(query)
    c_numbers = extract_numbers(candidate)
    q_year = extract_year(query)
    c_year = extract_year(candidate)
    q_core = canonical_tokens(query, drop_descriptors=True)
    c_core = canonical_tokens(candidate, drop_descriptors=True)
    q_all_canon = canonical_tokens(query, drop_descriptors=False)
    c_all_canon = canonical_tokens(candidate, drop_descriptors=False)

    token_set = fuzz.token_set_ratio(q_norm, c_norm) / 100.0
    token_sort = fuzz.token_sort_ratio(q_norm, c_norm) / 100.0
    ratio = fuzz.ratio(q_norm, c_norm) / 100.0
    partial = fuzz.partial_ratio(q_norm, c_norm) / 100.0

    q_compact = "".join(q_tokens)
    c_compact = "".join(c_tokens)

    features = [
        token_set,
        token_sort,
        ratio,
        partial,
        1.0 if q_norm == c_norm else 0.0,
        1.0 if q_compact == c_compact else 0.0,
        1.0 if q_norm in c_norm and q_norm != c_norm else 0.0,
        1.0 if c_norm in q_norm and q_norm != c_norm else 0.0,
        1.0 if descriptor_stripped_match(query, candidate) else 0.0,
        1.0 if q_core and q_core == c_core else 0.0,
        1.0 if q_all_canon and q_all_canon == c_all_canon else 0.0,
        jaccard(q_tokens, c_tokens),
        jaccard(q_meaning, c_meaning),
        jaccard(q_dist, c_dist),
        jaccard(q_core, c_core),
        overlap_fraction(q_meaning, c_meaning),
        overlap_fraction(q_dist, c_dist),
        overlap_fraction(q_core, c_core),
        1.0 if q_numbers == c_numbers and q_numbers else 0.0,
        1.0 if q_numbers and c_numbers and q_numbers != c_numbers else 0.0,
        1.0 if sequence_conflict(query, candidate) else 0.0,
        1.0 if not q_numbers else 0.0,
        1.0 if not c_numbers else 0.0,
        1.0 if q_year == c_year and q_year is not None else 0.0,
        1.0 if q_year is not None and c_year is not None and q_year != c_year else 0.0,
        1.0 if franchise_key(query) and franchise_key(query) == franchise_key(candidate) else 0.0,
        abs(len(q_norm) - len(c_norm)) / max(1, max(len(q_norm), len(c_norm))),
        len(set(q_tokens) & set(c_tokens)),
        len(set(q_dist) & set(c_dist)),
        float(len([tok for tok in c_core if tok not in q_core])),
        float(len([tok for tok in q_core if tok not in c_core]))
    ]
    return features


def sigmoid(value):
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


class LogisticModel:
    def __init__(self, size):
        self.weights = [0.0] * size
        self.bias = 0.0

    def predict_proba(self, features):
        score = self.bias
        for weight, feature in zip(self.weights, features):
            score += weight * feature
        return sigmoid(score)

    def fit(self, dataset, epochs=14, learning_rate=0.15, l2=0.0005):
        rng = random.Random(42)
        for _ in range(epochs):
            rng.shuffle(dataset)
            for features, label in dataset:
                pred = self.predict_proba(features)
                error = pred - label
                for index, feature in enumerate(features):
                    self.weights[index] -= learning_rate * (error * feature + l2 * self.weights[index])
                self.bias -= learning_rate * error

    def to_dict(self):
        return {"bias": self.bias, "weights": self.weights}


def build_indexes(apps):
    by_id = {}
    by_norm = defaultdict(list)
    inverted = defaultdict(set)
    for app in apps:
        by_id[app["appid"]] = app["name"]
        norm = normalize(app["name"])
        by_norm[norm].append(app)
        for token in set(meaningful_tokens(app["name"])):
            inverted[token].add(app["appid"])
    return by_id, by_norm, inverted


def candidate_ids_for_title(title, apps, inverted):
    tokens = meaningful_tokens(title)
    candidate_ids = set()
    for token in tokens:
        candidate_ids.update(inverted.get(token, set()))

    return candidate_ids


def build_training_examples(downloads, apps, by_id, inverted, max_positives=0):
    positives = []
    negatives = []
    app_lookup = {app["appid"]: app["name"] for app in apps}
    apps_by_id = {app["appid"]: app for app in apps}
    rng = random.Random(42)

    eligible = []
    for item in downloads:
        steam = item.get("steam") or {}
        appid = steam.get("steam_appid")
        title = item.get("title")
        if appid and title and appid in app_lookup:
            eligible.append((title, appid, app_lookup[appid]))

    rng.shuffle(eligible)
    selected = eligible if not max_positives or max_positives >= len(eligible) else eligible[:max_positives]

    for title, appid, true_name in selected:
        positives.append((title, true_name))

        candidates = []
        for candidate_id in candidate_ids_for_title(title, apps, inverted):
            if candidate_id == appid:
                continue
            candidate_name = apps_by_id[candidate_id]["name"]
            q_norm = normalize(title)
            c_norm = normalize(candidate_name)
            score = (
                0.5 * fuzz.token_set_ratio(q_norm, c_norm) +
                0.3 * fuzz.ratio(q_norm, c_norm) +
                0.2 * fuzz.partial_ratio(q_norm, c_norm)
            )
            if score >= 60:
                candidates.append((score, candidate_name))

        candidates.sort(reverse=True)
        added = 0
        for _, candidate_name in candidates[:6]:
            negatives.append((title, candidate_name))
            added += 1
        if added == 0:
            for app in rng.sample(apps, min(2, len(apps))):
                if app["appid"] != appid:
                    negatives.append((title, app["name"]))

    return positives, negatives


def build_synthetic_positive_examples(apps, limit=4000):
    synthetic = []
    seen = set()
    for app in apps:
        candidate = app["name"]
        for variant in synthetic_query_variants(candidate):
            key = (variant, candidate)
            if key in seen:
                continue
            if canonical_text(variant, drop_descriptors=True) != canonical_text(candidate, drop_descriptors=True):
                continue
            seen.add(key)
            synthetic.append(key)
            if len(synthetic) >= limit:
                return synthetic
    return synthetic


def build_franchise_negative_examples(apps, limit=3000):
    grouped = defaultdict(list)
    negatives = []
    seen = set()

    for app in apps:
        key = franchise_key(app["name"])
        numbers = extract_numbers(app["name"])
        if key and numbers:
            grouped[key].append(app["name"])

    for key, names in grouped.items():
        if len(names) < 2:
            continue
        for query_name in names:
            query_numbers = extract_numbers(query_name)
            for candidate_name in names:
                if query_name == candidate_name:
                    continue
                candidate_numbers = extract_numbers(candidate_name)
                if not candidate_numbers or query_numbers == candidate_numbers:
                    continue
                pair = (remove_trailing_descriptors(query_name), candidate_name)
                if pair in seen:
                    continue
                seen.add(pair)
                negatives.append(pair)
                if len(negatives) >= limit:
                    return negatives
    return negatives


def split_pairs(pairs, ratio=0.8):
    rng = random.Random(42)
    pairs = pairs[:]
    rng.shuffle(pairs)
    cut = int(len(pairs) * ratio)
    return pairs[:cut], pairs[cut:]


def to_dataset(positives, negatives):
    dataset = []
    for query, candidate in positives:
        dataset.append((feature_vector(query, candidate), 1.0))
    for query, candidate in negatives:
        dataset.append((feature_vector(query, candidate), 0.0))
    return dataset


def evaluate(model, positives, negatives):
    tp = fp = tn = fn = 0
    for query, candidate in positives:
        pred = model.predict_proba(feature_vector(query, candidate)) >= 0.5
        if pred:
            tp += 1
        else:
            fn += 1
    for query, candidate in negatives:
        pred = model.predict_proba(feature_vector(query, candidate)) >= 0.5
        if pred:
            fp += 1
        else:
            tn += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn
    }


def evaluate_manual_cases(model):
    if not MANUAL_CASES_PATH.exists():
        return {}

    with open(MANUAL_CASES_PATH, "r", encoding="utf-8") as handle:
        cases = json.load(handle)

    report = {"positive": [], "negative": []}
    for label in ("positive", "negative"):
        expected = 1.0 if label == "positive" else 0.0
        for query, candidate in cases.get(label, []):
            probability = model.predict_proba(feature_vector(query, candidate))
            predicted = 1.0 if probability >= 0.5 else 0.0
            report[label].append({
                "query": query,
                "candidate": candidate,
                "probability": round(probability, 4),
                "correct": predicted == expected
            })
    return report


def save_model(model, metrics, manual):
    payload = {
        "bias": model.bias,
        "weights": model.weights,
        "threshold": 0.5,
        "metrics": metrics,
        "manual_cases": manual
    }
    with open(MODEL_OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-positives", type=int, default=0)
    parser.add_argument("--manual-positive-weight", type=int, default=12)
    parser.add_argument("--manual-negative-weight", type=int, default=4)
    parser.add_argument("--synthetic-positive-limit", type=int, default=4000)
    parser.add_argument("--synthetic-positive-weight", type=int, default=3)
    parser.add_argument("--franchise-negative-limit", type=int, default=3000)
    parser.add_argument("--franchise-negative-weight", type=int, default=3)
    parser.add_argument("--catalog-edge-positive-limit", type=int, default=45)
    parser.add_argument("--catalog-edge-positive-weight", type=int, default=4)
    parser.add_argument("--catalog-edge-negative-limit", type=int, default=120)
    parser.add_argument("--catalog-edge-negative-weight", type=int, default=4)
    args = parser.parse_args()

    with open(ONLINE_FIX_PATH, "r", encoding="utf-8-sig") as handle:
        downloads = json.load(handle)["downloads"]
    with open(STEAM_CATALOG_PATH, "r", encoding="utf-8-sig") as handle:
        apps = json.load(handle)["apps"]

    by_id, _by_norm, inverted = build_indexes(apps)
    positives, negatives = build_training_examples(downloads, apps, by_id, inverted, max_positives=args.max_positives)
    synthetic_positives = build_synthetic_positive_examples(apps, limit=args.synthetic_positive_limit)
    franchise_negatives = build_franchise_negative_examples(apps, limit=args.franchise_negative_limit)
    catalog_edge_positives = generate_catalog_edge_positive_examples(apps, per_category=args.catalog_edge_positive_limit)
    catalog_edge_negatives = generate_catalog_edge_negative_examples(apps, family_limit=args.catalog_edge_negative_limit)
    for case in synthetic_positives:
        positives.extend([case] * max(1, args.synthetic_positive_weight))
    for case in franchise_negatives:
        negatives.extend([case] * max(1, args.franchise_negative_weight))
    for case in catalog_edge_positives:
        positives.extend([(case["query"], case["candidate"])] * max(1, args.catalog_edge_positive_weight))
    for case in catalog_edge_negatives:
        negatives.extend([(case["query"], case["candidate"])] * max(1, args.catalog_edge_negative_weight))

    if MANUAL_CASES_PATH.exists():
        with open(MANUAL_CASES_PATH, "r", encoding="utf-8") as handle:
            manual_cases = json.load(handle)
        for case in manual_cases.get("positive", []):
            positives.extend([tuple(case)] * max(1, args.manual_positive_weight))
        for case in manual_cases.get("negative", []):
            negatives.extend([tuple(case)] * max(1, args.manual_negative_weight))

    train_pos, test_pos = split_pairs(positives)
    train_neg, test_neg = split_pairs(negatives)

    train_data = to_dataset(train_pos, train_neg)
    model = LogisticModel(len(train_data[0][0]))
    model.fit(train_data)

    metrics = evaluate(model, test_pos, test_neg)
    manual = evaluate_manual_cases(model)

    print("Training positives:", len(train_pos))
    print("Training negatives:", len(train_neg))
    print("Test positives:", len(test_pos))
    print("Test negatives:", len(test_neg))
    print("Synthetic positives:", len(synthetic_positives))
    print("Franchise negatives:", len(franchise_negatives))
    print("Catalog edge positives:", len(catalog_edge_positives))
    print("Catalog edge negatives:", len(catalog_edge_negatives))
    print("Metrics:", json.dumps(metrics, ensure_ascii=False, indent=2))

    save_model(model, metrics, manual)
    print("Model saved to:", MODEL_OUTPUT_PATH)
    if manual:
        print("Manual cases:")
        safe_json = json.dumps(manual, ensure_ascii=True, indent=2)
        print(safe_json)


if __name__ == "__main__":
    main()
