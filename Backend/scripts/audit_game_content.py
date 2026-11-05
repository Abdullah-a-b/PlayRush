"""غربلة أولية للنسخ الاحتياطية فقط؛ لا قاعدة بيانات ولا تعديل/حذف لأي سجل.
python scripts/audit_game_content.py --backup-dir PATH --output report.json
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.import_support import canonical, read_json, atomic_json


def audit(backup):
    backup = Path(backup)
    issues = []; counts = {}
    def flag(game, ident, reason): issues.append({"game": game, "id": ident, "reason": reason})
    def duplicates(game, rows, field, reason):
        seen = {}
        for row in rows:
            key = canonical(row.get(field))
            if key and key in seen: flag(game, row.get("id"), reason)
            elif key: seen[key] = row.get("id")
    questions = read_json(backup / "questions.json", [])
    counts["huroof"] = len(questions)
    duplicates("huroof", questions, "question_text", "duplicate_question_text")
    for q in questions:
        if not q.get("correct_answer"): flag("huroof", q.get("id"), "empty_answer")
        try:
            extra = json.loads(q.get("extra_data") or '{}')
            if not isinstance(extra, dict): raise ValueError()
        except (ValueError, TypeError): flag("huroof", q.get("id"), "invalid_metadata")
    players = read_json(backup / "career_players.json", [])
    counts["career"] = len(players)
    duplicates("career", players, "wikidata_id", "duplicate_wikidata_id")
    duplicates("career", players, "name", "duplicate_player_name")
    aliases = defaultdict(set)
    for player in players:
        pid = player.get("id")
        for field in ("clubs", "accepted_answers"):
            try:
                values = json.loads(player.get(field) or '[]')
                if not isinstance(values, list): raise ValueError()
            except (ValueError, TypeError): flag("career", pid, "invalid_" + field);continue
            if field == "clubs":
                if not values: flag("career", pid, "no_clubs")
                if any(not isinstance(c, dict) or re.fullmatch(r"Q[0-9]+", str(c.get("name", ""))) for c in values): flag("career", pid, "unresolved_club_identity")
            else:
                for alias in values:
                    if not isinstance(alias, str): flag("career", pid, "invalid_alias");continue
                    aliases[canonical(alias)].add(pid)
                parts = str(player.get("name", "")).split()
                if len(parts) > 1 and canonical(parts[0]) in {canonical(a) for a in values if isinstance(a, str)}: flag("career", pid, "first_name_only_alias")
        if player.get("status") == "retired" and "الآن" in str(player.get("era", "")): flag("career", pid, "retired_with_present_era")
    for alias, ids in aliases.items():
        if alias and len(ids) > 1:
            for pid in sorted(ids): flag("career", pid, "alias_shared_by_multiple_players")
    for name in ("bank_questions", "bank_questions_auto"):
        rows = read_json(backup / (name + ".json"), [])
        counts[name] = len(rows)
        duplicates(name, rows, "id", "duplicate_id")
        duplicates(name, rows, "q", "duplicate_question_text")
    combined = read_json(backup / 'bank_questions.json', []) + read_json(backup / 'bank_questions_auto.json', [])
    duplicates("bank_combined", combined, "q", "manual_auto_duplicate_text")
    chars = read_json(backup / 'whoami_characters.json', {}).get('characters', [])
    counts['whoami'] = len(chars)
    duplicates('whoami', chars, 'id', 'duplicate_id');duplicates('whoami', chars, 'name', 'duplicate_name')
    for char in chars:
        if len(char.get('hints', [])) != 5: flag('whoami', char.get('id'), 'not_five_hints')
        if any('قيد الحياة' in str(h) for h in char.get('hints', [])): flag('whoami', char.get('id'), 'life_claim_requires_source_review')
    lists = read_json(backup / 'knowledge_questions.json', {}).get('questions', [])
    counts['knowledge'] = len(lists)
    duplicates('knowledge', lists, 'id', 'duplicate_id')
    for q in lists:
        keys = [canonical(str(a).split('|')[0]) for a in q.get('answers', [])]
        if len(keys) != len(set(keys)): flag('knowledge', q.get('id'), 'duplicate_normalized_answers')
    return {"mode": "read_only", "counts": counts, "issue_count": len(issues), "issues": issues, "limitation": "Structural checks and review flags; not a factual verification or authorization to delete."}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.backup_dir)
    atomic_json(args.output, result)
    print(json.dumps({"counts": result['counts'], "review_flags": result['issue_count'], "changed_records": 0}, ensure_ascii=False))
