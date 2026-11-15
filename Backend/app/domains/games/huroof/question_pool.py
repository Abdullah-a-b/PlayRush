"""اختيار أسئلة مناسبة للمستوى ومتنوعة؛ حجم تصنيف في القاعدة لا يعطيه أفضلية."""
from collections import Counter
import random

from app.core.huroof_answers import _core

# الصعب يظل تحدياً محدوداً؛ أسئلة الحفظ النادرة ليست أسئلة اللعب العادي.
QUESTION_MIX = {
    'beginner': {'easy': .80, 'medium': .20},
    'medium': {'easy': .60, 'medium': .35, 'hard': .05},
    'hard': {'easy': .40, 'medium': .50, 'hard': .10},
    'expert': {'easy': .30, 'medium': .55, 'hard': .15},
    'online': {'easy': .65, 'medium': .30, 'hard': .05},
}


def choose_question(rows, letter, used_ids=(), seen_ids=(), *, level='online',
                    preferred_category=None, used_answers=(), rng=None):
    """نوازن الصعوبة أولاً؛ لا تدفعنا رؤية السهل سابقاً إلى سؤال مستحيل."""
    rng = rng or random
    mix = QUESTION_MIX.get(level, QUESTION_MIX['online'])
    letter_rows = [q for q in rows if letter in q.get('valid_letters', ())]
    eligible = [q for q in letter_rows if q.get('difficulty', 'medium') in mix]
    if not eligible:
        # لا نعيد سؤالاً نادراً بصمت حين يفتقر حرف للمحتوى؛ المتصل يختار حرفاً مغطّى.
        return None
    used, seen = set(used_ids), set(seen_ids)
    unused = [q for q in eligible if q['id'] not in used]
    eligible = unused or eligible
    answer_keys = {_core(answer) for answer in used_answers}
    new_answers = [q for q in eligible if _core(q['correct_answer']) not in answer_keys]
    eligible = new_answers or eligible
    if preferred_category:
        preferred = [q for q in eligible if q['category'] == preferred_category]
        eligible = preferred or eligible
    by_id = {q['id']: q for q in rows}
    recent = [by_id[qid] for qid in list(used_ids)[-4:] if qid in by_id]
    if not preferred_category:
        # لا تتكرر الكيمياء والجغرافيا معاً على حساب بقية الأنواع إن وُجد بديل.
        for category in ('جغرافيا', 'دين'):
            if any(q['category'] == category for q in recent):
                other = [q for q in eligible if q['category'] != category]
                eligible = other or eligible
        if any(q.get('chemistry') for q in recent):
            other = [q for q in eligible if not q.get('chemistry')]
            eligible = other or eligible
    bands = [name for name in mix if any(q.get('difficulty', 'medium') == name for q in eligible)]
    band = rng.choices(bands, weights=[mix[name] for name in bands], k=1)[0]
    candidates = [q for q in eligible if q.get('difficulty', 'medium') == band]
    fresh = [q for q in candidates if q['id'] not in seen]
    candidates = fresh or candidates
    if not preferred_category:
        counts = Counter(q['category'] for q in recent)
        lowest = min(counts[q['category']] for q in candidates)
        candidates = [q for q in candidates if counts[q['category']] == lowest]
        # اختيار التصنيف أولاً، ثم السؤال: لا تطغى 500 جغرافيا على 10 رياضة.
        category = rng.choice(sorted({q['category'] for q in candidates}))
        candidates = [q for q in candidates if q['category'] == category]
    return rng.choice(candidates)
