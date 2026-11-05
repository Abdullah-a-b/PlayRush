"""بدائل إملائية مراجعة؛ لا استبدال عشوائي للحروف ولا حذف أحرف من الإجابة.

الاسم الأصلي وبلا «ال» والإنجليزي محفوظون. الاختلافات العامة (التشكيل
وأشكال الألف) تعالجها طبقة التطبيع. الأسماء الأجنبية تحتاج بدائل مراجعة
محددة، لا قاعدة تحول كل ج إلى غ أو تحذف ألفاً من أي كلمة.
"""
_REVIEWED_GROUPS = [frozenset({'سانتياغو', 'سانتياجو', 'سنتياغو', 'سنتياجو'})]


def spelling_variants(ar, en=None, cap=15):
    ar = (ar or '').strip()
    if not ar:
        return []
    base = {ar}
    bare = ar[2:] if ar.startswith('ال') and len(ar) > 4 else ar
    base.add(bare)
    reviewed = set()
    for group in _REVIEWED_GROUPS:
        if bare in group:
            reviewed.update(group)
    out = sorted(base) + sorted(reviewed - base)[:max(0, cap - len(base))]
    if en:
        out.append(en.strip().lower())
    return list(dict.fromkeys(v for v in out if v))
