# قائمة قصيرة لجمهور الثقافة العامة؛ بقية المهن تحتفظ بمصادرها.
SPORTS_STARS = {
    "Q937857": ("Q615", "Q11571", "Q12897", "Q17515", "Q1835", "Q1354960"),
    "Q10833314": ("Q1426", "Q10132"),
    "Q3665646": ("Q41421",),
    "Q11338576": ("Q36107",),
}

APPROVED_IDS = frozenset(qid for group in SPORTS_STARS.values() for qid in group)
MANUAL_IDS = {"messi", "ronaldo", "pele", "maradona", "zidane", "salah"}


def approved_character(character):
    source = character.get("source")
    occupation = source.get("occupation") if isinstance(source, dict) else None
    if occupation not in SPORTS_STARS and "رياض" not in character.get("category", ""):
        return True
    qid = character.get("wikidata_id") or character.get("_curation", {}).get("wikidata_id")
    return qid in APPROVED_IDS if qid else character.get("id") in MANUAL_IDS
