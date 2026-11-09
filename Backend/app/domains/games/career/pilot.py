"""تجربة فردية ببيانات مراجعة وتحكيم أسماء محدد."""
import json
import random
import re
import unicodedata
from pathlib import Path


ROSTER = {
    player["id"]: player
    for player in json.loads(Path(__file__).with_name("pilot_roster.json").read_text(encoding="utf-8"))
}
_NAME_CHARS = str.maketrans("ٱىیک٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "اييك01234567890123456789")
_DECORATION = re.compile(r"[ـ\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def normalize_name(value):
    text = unicodedata.normalize("NFKD", value.casefold()).translate(_NAME_CHARS)
    text = _DECORATION.sub("", text)
    text = "".join(char for char in text if not unicodedata.category(char).startswith("M"))
    return " ".join(re.findall(r"[^\W_]+", text))


def accepts_name(answer, player):
    if not isinstance(answer, str) or len(answer) > 120:
        return False
    guess = normalize_name(answer)
    variants = (player["name"], *player["accepted_answers"])
    return bool(guess) and any(guess == normalize_name(name) for name in variants)


def round_order():
    tiers = {
        tier: [pid for pid, player in ROSTER.items() if player["difficulty"] == tier]
        for tier in ("easy", "medium", "hard")
    }
    for players in tiers.values():
        random.shuffle(players)
    easy, medium, hard = (tiers[tier] for tier in ("easy", "medium", "hard"))
    opening = easy[:2] + medium[:2] + hard[:1]
    reserve = easy[2:] + medium[2:] + hard[1:]
    random.shuffle(opening)
    random.shuffle(reserve)
    return opening + reserve


def _club_key(club):
    return normalize_name(club["name"].removesuffix(" (إعارة)"))


def matching_players(visible_clubs, complete=False):
    names = [_club_key(club) for club in visible_clubs]
    if not names:
        return []
    return [
        player for player in ROSTER.values()
        if (not complete or len(player["clubs"]) == len(names))
        and names == [_club_key(club) for club in player["clubs"][:len(names)]]
    ]
