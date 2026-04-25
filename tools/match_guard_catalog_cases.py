import json
import re
from collections import Counter, defaultdict


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
    "launch", "steam", "store", "full", "s", "classic", "legacy"
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
    text = re.sub(r"[':!?,.%&()+\[\]{}|/\\\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def textual_tokens(text):
    return re.findall(r"[a-z0-9]+", normalize(text))


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


def extract_numbers(text):
    numbers = [int(x) for x in re.findall(r"\b\d{1,4}\b", text or "")]
    roman = [ROMAN_VALUES[tok] for tok in textual_tokens(text) if tok in ROMAN_VALUES]
    return sorted(set(numbers + roman))


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


def strip_parenthetical_suffix(text):
    return re.sub(r"\s*\([^)]*\)\s*$", "", text or "").strip()


def strip_year_tokens(text):
    return re.sub(r"\b(?:19\d{2}|20\d{2})\b", "", text or "").replace("()", "").strip()


def replace_ampersand(text):
    return (text or "").replace("&", "and")


def remove_apostrophes(text):
    return (text or "").replace("'", "").replace("’", "")


def collapse_punctuation(text):
    text = text or ""
    text = text.replace(":", " ").replace("-", " ").replace("–", " ").replace("—", " ")
    text = text.replace("™", " ").replace("®", " ").replace("©", " ")
    return re.sub(r"\s+", " ", text).strip()


def catalog_pattern_stats(apps):
    patterns = {
        "colon": lambda s: ":" in s,
        "apostrophe": lambda s: "'" in s or "’" in s,
        "ampersand": lambda s: "&" in s,
        "roman": lambda s: bool(re.search(r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI)\b", s)),
        "year": lambda s: bool(re.search(r"\b(?:19\d{2}|20\d{2})\b", s)),
        "edition": lambda s: "Edition" in s or "edition" in s,
        "dash": lambda s: "-" in s or "–" in s or "—" in s,
        "paren": lambda s: "(" in s or ")" in s,
        "non_ascii": lambda s: any(ord(c) > 127 for c in s),
        "long_8p": lambda s: len((s or "").split()) >= 8,
    }
    counts = Counter()
    for app in apps:
        name = app["name"] or ""
        for key, fn in patterns.items():
            if fn(name):
                counts[key] += 1
    return dict(counts)


def _edge_categories():
    return {
        "apostrophe": (
            lambda s: "'" in s or "’" in s,
            [remove_apostrophes, collapse_punctuation],
        ),
        "ampersand": (
            lambda s: "&" in s,
            [replace_ampersand, collapse_punctuation],
        ),
        "colon": (
            lambda s: ":" in s,
            [collapse_punctuation, lambda s: strip_parenthetical_suffix(s.split(":", 1)[0].strip())],
        ),
        "roman": (
            lambda s: bool(re.search(r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI)\b", s)),
            [collapse_punctuation],
        ),
        "year": (
            lambda s: bool(re.search(r"\b(?:19\d{2}|20\d{2})\b", s)),
            [strip_year_tokens, strip_parenthetical_suffix],
        ),
        "edition": (
            lambda s: "Edition" in s or "edition" in s,
            [remove_trailing_descriptors, strip_parenthetical_suffix],
        ),
        "paren": (
            lambda s: "(" in s or ")" in s,
            [strip_parenthetical_suffix, collapse_punctuation],
        ),
        "non_ascii": (
            lambda s: any(ord(c) > 127 for c in s),
            [collapse_punctuation],
        ),
        "long_8p": (
            lambda s: len((s or "").split()) >= 8,
            [collapse_punctuation, strip_parenthetical_suffix],
        ),
    }


def generate_catalog_edge_positive_examples(apps, per_category=40):
    cases = []
    seen = set()
    core_counts = Counter()
    for app in apps:
        core = canonical_text(app["name"], drop_descriptors=True)
        if core:
            core_counts[core] += 1
    for category, (predicate, transforms) in _edge_categories().items():
        added = 0
        for app in apps:
            if added >= per_category:
                break
            name = app["name"] or ""
            if not predicate(name):
                continue
            expected_core = canonical_text(name, drop_descriptors=True)
            if not expected_core or core_counts[expected_core] != 1:
                continue
            for transform in transforms:
                query = transform(name)
                if not query:
                    continue
                if normalize(query) == normalize(name):
                    continue
                if canonical_text(query, drop_descriptors=True) != expected_core:
                    continue
                key = (category, query, name)
                if key in seen:
                    continue
                seen.add(key)
                cases.append({
                    "category": category,
                    "query": query,
                    "candidate": name,
                    "appid": app["appid"],
                })
                added += 1
                break
    return cases


def generate_catalog_edge_negative_examples(apps, per_family=2, family_limit=120):
    grouped = defaultdict(list)
    cases = []
    seen = set()
    for app in apps:
        name = app["name"] or ""
        key = franchise_key(name)
        numbers = extract_numbers(name)
        if key and numbers:
            grouped[key].append(app)

    families_used = 0
    for _key, family_apps in grouped.items():
        uniq = []
        seen_names = set()
        for app in family_apps:
            if app["name"] not in seen_names:
                seen_names.add(app["name"])
                uniq.append(app)
        uniq.sort(key=lambda item: normalize(item["name"]))
        family_added = 0
        for query_app in uniq:
            query_numbers = extract_numbers(query_app["name"])
            for candidate_app in uniq:
                if query_app["appid"] == candidate_app["appid"]:
                    continue
                candidate_numbers = extract_numbers(candidate_app["name"])
                if not candidate_numbers or query_numbers == candidate_numbers:
                    continue
                query = remove_trailing_descriptors(query_app["name"])
                if franchise_key(query) != franchise_key(candidate_app["name"]):
                    continue
                key = (query, candidate_app["name"])
                if key in seen:
                    continue
                seen.add(key)
                cases.append({
                    "category": "franchise_number_conflict",
                    "query": query,
                    "candidate": candidate_app["name"],
                    "expected_appid": query_app["appid"],
                    "wrong_appid": candidate_app["appid"],
                })
                family_added += 1
                if family_added >= per_family:
                    break
            if family_added >= per_family:
                break
        if family_added:
            families_used += 1
        if families_used >= family_limit:
            break
    return cases


def dump_cases_preview(cases, limit=12):
    return json.dumps(cases[:limit], ensure_ascii=True, indent=2)
