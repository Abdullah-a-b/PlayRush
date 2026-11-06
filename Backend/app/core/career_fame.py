"""تصنيف شهرة اللاعبين المُراجع؛ مؤشرات الويب أدلة مساعدة وليست استطلاعًا."""
from app.core import paths
from app.core.import_support import read_json

TIERS = {'easy', 'medium', 'hard'}
_CACHE = {'key': None, 'players': {}}


def profiles():
    path = paths.DATA_DIR / 'career_fame_review.json'
    if not path.exists():
        raise RuntimeError('ملف مراجعة الشهرة غير متاح؛ لم نغير تصنيفات اللاعبين')
    key = (str(path), path.stat().st_mtime_ns)
    if _CACHE['key'] != key:
        document = read_json(path, {'players': {}})
        players = document.get('players', {})
        if not isinstance(players, dict):
            raise ValueError('ملف مراجعة الشهرة غير صالح')
        for qid, profile in players.items():
            if profile.get('status') == 'reviewed' and profile.get('fame') not in TIERS:
                raise ValueError('تصنيف شهرة مُراجع غير معروف: ' + qid)
            if profile.get('career_memory', 'standard') not in {'standard', 'specialist'}:
                raise ValueError('تصنيف معرفة المسيرة غير معروف: ' + qid)
        _CACHE.update(key=key, players=players)
    return _CACHE['players']


def reviewed_classification(qid, current=None):
    profile = profiles().get(qid, {})
    eligible = profile.get('status') == 'reviewed' and profile.get('fame') in TIERS
    return {'difficulty': profile['fame'] if eligible else (current if current in TIERS else 'hard'),
            'eligible': eligible, 'status': profile.get('status', 'pending_review'),
            'career_memory': profile.get('career_memory', 'standard')}
