"""مطابقة إجابات حروف الكاملة دون قبول بادئة اسم مختلف."""
import re
import unicodedata
from app.core.text_processor import normalize_arabic


def _clean(value):
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    return ''.join(ch for ch in text if unicodedata.category(ch) not in {'Mn', 'Cf'} and ch != 'ـ')


def _core(value):
    text = _clean(value)
    # لا نحذف همزة «ألبانيا» أو مدّة «آل عمران» كأداة تعريف.
    return text[2:] if text.startswith(('ال', 'ٱل')) else text


def answer_letter(value):
    core = _core(value)
    if not core:
        return ''
    return {'ا':'أ', 'إ':'أ', 'آ':'أ', 'ٱ':'أ', 'ؤ':'و', 'ئ':'ي', 'ى':'ي', 'ة':'ه'}.get(core[0], core[0])


def _forms(value):
    return {re.sub(r'\s+', '', normalize_arabic(v)) for v in (_clean(value), _core(value))} - {''}


_HELSINKI_FORMS = {"هلسنكي", "هيلسينكي", "هيلسنكي", "هلسينكي"}


def check_answer(player_ans, correct_ans, accepted_list=None, required_letter=None):
    submitted = _forms(player_ans)
    candidates = [correct_ans] + (accepted_list if isinstance(accepted_list, list) else [])
    required = answer_letter(required_letter) if required_letter else None
    for candidate in candidates:
        candidate_forms = _forms(candidate)
        if (submitted & candidate_forms
                or (submitted & _HELSINKI_FORMS and candidate_forms & _HELSINKI_FORMS)):
            if required and answer_letter(candidate) != required:
                continue
            return {'verdict': 'accept', 'source': 'reviewed_alias'}
    return {'verdict': 'reject', 'source': 'full_answer_required'}
