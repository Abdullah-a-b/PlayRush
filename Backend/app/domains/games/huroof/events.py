import asyncio
import html
import random
import json
import time
import secrets
import string

# ==========================================
# الاستيرادات من الهيكلة الجديدة (تأكد من مطابقتها لمساراتك)
# ==========================================
from app.infrastructure.database import SessionLocal
from app.domains.games.models import Question
from app.domains.users.models import User
from app.domains.games.core_manager import get_room_state, rooms
from app.domains.games.huroof.engine import HuroofGameState
from app.domains.wallet.reward_service import record_match_result
from app.infrastructure.telegram_bot import send_secret_to_mobile

# ==========================================
# كاش أسئلة حروف بالذاكرة (إصلاح bottleneck حرج)
# كان trigger_new_question يسحب جدول Question *كاملاً* من DB
# ويحلّل JSON لكل صف — عند كل سؤال في كل مباراة!
# الآن: تحميل + تحليل مرة كل 10 دقائق، والفلترة بالذاكرة.
# ==========================================
_HUROOF_QCACHE = {'ts': 0.0, 'rows': None}
_HUROOF_QCACHE_TTL = 600  # الأسئلة تتغير عبر استيراد/سكربتات نادرة فقط


def _load_huroof_questions_cached():
    """(يعمل في thread) أسئلة حروف محلّلة مسبقاً — DB مرة كل 10 دقائق بدل كل سؤال."""
    now = time.time()
    if _HUROOF_QCACHE['rows'] is not None and (now - _HUROOF_QCACHE['ts']) < _HUROOF_QCACHE_TTL:
        return _HUROOF_QCACHE['rows']
    db = SessionLocal()
    try:
        rows = []
        for q in db.query(Question).filter(Question.game_mode == "huroof").all():
            try:
                extra = json.loads(q.extra_data) if q.extra_data else {}
            except Exception:
                extra = {}
            ans = (q.correct_answer or '').strip()
            core = ans[2:] if ans.startswith("ال") else ans
            # الحرف المميّز = الحرف الأول بعد إزالة "ال" التعريف.
            # "البحرين" → ب (لا ا)، "السعودية" → س، "الكويت" → ك.
            # لا نضيف حرف "ال" نفسه — يُصنّف السؤال خطأ تحت الألف.
            main_letter = normalize_letter(core[0]) if core else ''
            valid_letters = {main_letter} if main_letter else set()
            rows.append({
                'id': q.id,
                'question_text': q.question_text,
                'correct_answer': q.correct_answer,
                'category': q.category,
                'difficulty': (extra.get('difficulty') if extra.get('difficulty') in ('easy','medium','hard') else 'medium'),
                'accepted_answers': extra.get('accepted_answers', []),
                'letter_extra': normalize_letter(extra.get('letter', '') or ''),
                'letter_ans': main_letter,
                'valid_letters': valid_letters,
            })
        _HUROOF_QCACHE['rows'] = rows
        _HUROOF_QCACHE['ts'] = now
        return rows
    finally:
        db.close()


def _fetch_combined_seen(uids):
    """(يعمل في thread) مشاهدات اللاعبَين معاً — جلب بالـ id المفهرس.
    كان البحث بـ session_token *غير المفهرس* = مسح جدول users كاملاً ×2 لكل سؤال!"""
    combined = set()
    if not uids:
        return combined
    db = SessionLocal()
    try:
        for u in db.query(User).filter(User.id.in_(uids)).all():
            try:
                combined.update(json.loads(u.seen_question_ids or "[]"))
            except Exception:
                pass
    finally:
        db.close()
    return combined


def _mark_seen_thread(uids, qid):
    """(يعمل في thread — fire-and-forget) يضيف السؤال لمشاهدات اللاعبَين."""
    if not uids:
        return
    try:
        db = SessionLocal()
        try:
            for u in db.query(User).filter(User.id.in_(uids)).all():
                try:
                    seen = json.loads(u.seen_question_ids or "[]")
                except Exception:
                    seen = []
                if qid not in seen:
                    seen.append(qid)
                    u.seen_question_ids = json.dumps(seen)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f" [huroof] mark seen: {e}")


# المرحلة ب: نقطة الدخول الموحّدة للتحقق من أفعال اللاعب (BaseGame)
def _get_huroof_game():
    """يجلب نسخة HuroofGame المسجّلة في الإطار (للتحقق الموحّد)."""
    try:
        from app.domains.games.base import GameRegistry
        return GameRegistry.create('huroof', None)
    except Exception:
        return None

# نسخة واحدة مُعاد استخدامها (التحقق لا يحمل حالة)
_HUROOF_GAME = _get_huroof_game()

def _action_allowed(gs, sid, action_type):
    """تحقق موحّد عبر إطار BaseGame. يرجع True لو الفعل مسموح.
    طبقة تحقّق إضافية (لا تلغي فحوصات events.py الموجودة)."""
    if _HUROOF_GAME is None or gs is None:
        return True  # fallback: لا نكسر شيئاً لو الإطار غير متاح
    try:
        return _HUROOF_GAME.validate_action(gs, sid, action_type)
    except Exception:
        return True

# معالج النصوص العربية (Normalize  Fuzzy  Token)
from app.core.text_processor import check_answer

# Anti-Cheat (server-side validation)
from app.core.anticheat import (
    check_action_rate, check_human_reaction, check_payload_safety,
    validate_huroof_buzz, validate_huroof_answer,
    report_violation, is_temp_banned, Severity,
)

# ملاحظة هامة: القواميس العالمية مثل connected_players يجب أن تكون في ملف مشترك (مثلاً app/sockets/state.py)
from app.sockets.state import connected_players, disconnect_timers
# دالة العودة للوبي يجب أن تكون في ملف اللوبي
from app.domains.games.sockets.lobby import return_players_to_lobby

# ==========================================
# الفلاتر والدوال المساعدة للعبة حروف
# ==========================================
NORMALIZE_LETTER = {
    'ا': 'أ', 'إ': 'أ', 'آ': 'أ',
    'ة': 'ه', 'ى': 'ي', 'ؤ': 'و',
}

def normalize_letter(ch):
    return NORMALIZE_LETTER.get(ch, ch)

def advance_state(game_state, new_stage):
    """تحديث حالة اللعبة وزيادة رقم النسخة لمنع تداخل المؤقتات"""
    game_state.stage = new_stage
    game_state.state_version += 1
    return game_state.state_version

import re as _re

# محارف التشكيل والمحارف غير المرئية التي تُفشل المطابقة رغم تطابق الشكل
_AR_DIACRITICS = _re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]')
_INVISIBLE     = _re.compile(r'[\u0640\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]')
_PUNCT         = _re.compile(r'[\.\,\;\:\!\?\-\_\(\)\[\]\{\}«»"\'`ـ/\\]')

# تعريبات مختلفة لنفس الكلمة — تُطبَّق بعد التطبيع (بلا مسافات ولا تشكيل).
# محدّدة عمداً: لا نعمّم تبادل الحروف حتى لا تُقبل كلمات مختلفة المعنى.
_SPELLING_VARIANTS = [
    ('شيكل', 'شيقل'),        # عملة إسرائيل/فلسطين
    ('طوكيو', 'توكيو'),
    ('واشنطن', 'واشنطون'),
    ('موسكو', 'موسكوو'),
    ('بكين', 'بيجين'),
    ('استانبول', 'اسطنبول'),
    ('قطر', 'كطر'),
    ('جنيه', 'جنيهه'),
    ('يورو', 'اورو'),
    ('دولار', 'دولر'),
]

def clean_text_for_match(t):
    """تطبيع عربي شامل للتحكيم اللحظي.

    كان يعالج (ة/أ/إ/آ) فقط، فتفشل إجابات صحيحة بسبب فروق غير مرئية:
    التشكيل، التطويل، الكاف/الياء الفارسية، ومحارف الاتجاه المخفية.
    """
    t = str(t).strip()
    t = _INVISIBLE.sub('', t)
    t = _AR_DIACRITICS.sub('', t)       # حذف الحركات (شِيكِل → شيكل)
    t = _PUNCT.sub('', t)

    # توحيد صور الحروف
    t = (t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ٱ', 'ا')
          .replace('ة', 'ه')
          .replace('ى', 'ي').replace('ی', 'ي')      # ألف مقصورة وياء فارسية
          .replace('ك', 'ك').replace('ک', 'ك')      # كاف فارسية → عربية
          .replace('ؤ', 'و').replace('ئ', 'ي').replace('ء', ''))

    if t.startswith('ال'):
        t = t[2:]
    return t.replace(' ', '')


def _core_forms(text):
    """صيغ مقبولة للإجابة: الكاملة + الكلمة الأولى (للإجابات المركّبة).
    مثال: «شيكل إسرائيلي جديد» → يُقبل أيضاً «شيكل»."""
    raw = str(text).strip()
    forms = {clean_text_for_match(raw)}
    words = [w for w in _re.split(r'\s+', raw) if w]
    if len(words) > 1:
        forms.add(clean_text_for_match(words[0]))
        forms.add(clean_text_for_match(' '.join(words[:2])))

    # صيغ إملائية بديلة معتمدة (تعريب مختلف لنفس الكلمة).
    # قائمة محدّدة عمداً — لا نجعل ق=ك عموماً لأن ذلك يخلط كلمات مختلفة.
    extra = set()
    for f in forms:
        for a, b in _SPELLING_VARIANTS:
            if a in f: extra.add(f.replace(a, b))
            if b in f: extra.add(f.replace(b, a))
    forms |= extra
    return {f for f in forms if f}


def check_answer_fast_track(player_ans, correct_ans, accepted_list, required_letter):
    """التحكيم اللحظي (0 ملي ثانية)"""
    p_clean = clean_text_for_match(player_ans)
    req_clean = clean_text_for_match(required_letter)

    # 1. الكلمة لا تبدأ بالحرف المطلوب
    if not p_clean.startswith(req_clean):
        return False, "wrong_letter"

    # 2. تطابق مع الإجابة الرسمية أو إحدى صيغها المختصرة
    if p_clean in _core_forms(correct_ans):
        return True, "exact_match"

    # 3. تطابق مع قائمة المرادفات المسموحة (وصيغها المختصرة أيضاً)
    for acc in (accepted_list or []):
        if p_clean in _core_forms(acc):
            return True, "accepted_match"

    # 4. الإجابة جزء مطابق من بداية الإجابة الرسمية (٤ أحرف فأكثر)
    #    يقبل «شيكل» مقابل «شيكلإسرائيليجديد» بلا قبول تخمينات قصيرة.
    c_full = clean_text_for_match(correct_ans)
    if len(p_clean) >= 4 and c_full.startswith(p_clean):
        return True, "prefix_match"

    # 5. غير ذلك → المحكمة العليا (الذكاء الاصطناعي)
    return False, "إجابة خاطئة"


# ==========================================
# تسجيل أحداث السوكيت للعبة حروف
# ==========================================
# خطّافات الوضع الفردي: تُملأ داخل register، وتُستدعى من دوال اللعبة
# لإشعار البوت (فارغة تماماً في الأونلاين، فلا أثر عليه).
_SOLO_HOOKS = {}


def register_huroof_events(sio):
    """تغليف الدوال والأحداث لكي تتمكن من استخدام كائن sio"""

    async def emit_turn_changed(room_code, gs, turn_sid):
        """يبثّ تغيّر الدور بـ sid + اللون (اللون أكثر استقراراً عبر إعادة الاتصال)."""
        turn_color = 'green' if turn_sid == gs.p1 else 'orange'
        await sio.emit('huroof_turn_changed',
                       {'turn_sid': turn_sid, 'turn_color': turn_color},
                       room=room_code)
        # الوضع الفردي: لو صار الدور للبوت، يبدأ اختياره
        if getattr(gs, 'is_solo', False) and 'after_turn' in _SOLO_HOOKS:
            sio.start_background_task(_SOLO_HOOKS['after_turn'], room_code)

    def is_players_turn(room, gs, sid):
        """هل هذا الـ sid صاحب الدور؟ نتحقق عبر اللون (مستقر) لا الـ sid فقط،
        لتفادي رفض اللاعب الشرعي لو تغيّر sid (انتقال/إعادة اتصال)."""
        if gs.turn == sid:
            return True
        # نحدّد لون صاحب الدور فقط لو كان gs.turn يطابق أحد اللاعبين فعلاً
        if gs.turn == gs.p1:
            turn_color = 'green'
        elif gs.turn == gs.p2:
            turn_color = 'orange'
        else:
            return False  # gs.turn قديم/غير معروف — لا نخمّن
        for p in room.get('players', []):
            if p.get('color') == turn_color and p.get('sid') == sid:
                # نُحدّث gs.turn للـ sid الحالي (إصلاح ذاتي)
                gs.turn = sid
                if turn_color == 'green':
                    gs.p1 = sid
                else:
                    gs.p2 = sid
                return True
        return False

    async def huroof_timer_task(room_code, version, seconds, timeout_type):
        # نسجّل بيانات المؤقّت النشط (لمساعدة تمديد الوقت)
        _room0 = get_room_state(room_code)
        if _room0 and _room0.get('game_state'):
            import time as _t
            _room0['game_state'].active_timer = {
                'version': version, 'timeout_type': timeout_type,
                'ends_at': _t.time() + seconds
            }
        await asyncio.sleep(seconds)
        # رادار: هل الغرفة لا تزال موجودة وبحالة لعب؟
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return 
            
        gs = room['game_state']
        if gs.state_version != version: return
        
        # التحقق أن الحالة لم تتغير
        if gs.state_version == version:
            print(f"⏰ [Timeout] الغرفة {room_code} | النوع: {timeout_type}")
            
            if timeout_type == 'timeout_buzz_r1':
                # 0 لم يضغط أحد الجرس في الـ 40 ثانية -> فرصة أخيرة مباشرة
                gs.attempts = 2
                version = advance_state(gs, 'question')
                gs.buzzed_player = None
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')
                if getattr(gs, 'is_solo', False) and 'consider_buzz' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['consider_buzz'], room_code, version, 30)

            elif timeout_type == 'timeout_answer_r1':
                # 1 اللاعب الأول أضاع الـ 15 ثانية -> ينتقل للخصم بـ 20 ثانية (المحاولة الأولى)
                version = advance_state(gs, 'answer_r2')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 20, 'round': 'r2'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
                if getattr(gs, 'is_solo', False) and 'on_transfer' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['on_transfer'], room_code, version, 20)
                
            elif timeout_type == 'timeout_answer_r2':
                # 2 الخصم أضاع الـ 20 ثانية -> فشل الكل في الأولى، نفتح المحاولة الثانية
                gs.attempts = 2 
                version = advance_state(gs, 'question') 
                gs.buzzed_player = None
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')
                if getattr(gs, 'is_solo', False) and 'consider_buzz' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['consider_buzz'], room_code, version, 30)
                
            elif timeout_type == 'timeout_answer_r3':
                # 3 اللاعب أضاع الـ 12 ثانية (في المحاولة الثانية) -> ينتقل للخصم بـ 12 ثانية
                version = advance_state(gs, 'answer_r4')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 12, 'round': 'r4'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')
                if getattr(gs, 'is_solo', False) and 'on_transfer' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['on_transfer'], room_code, version, 12)

            elif timeout_type == 'timeout_answer_r4' or timeout_type == 'timeout_buzz_r3':
                # 4 انتهت كل الفرص أو لم يضغط أحد في الفرصة الثانية
                # 🆕 نكشف الإجابة الصحيحة للطرفين (استُنفدت كل المحاولات)
                _ca = gs.current_question.get('answer', '') if gs.current_question else ''
                if _ca:
                    await sio.emit('huroof_reveal_answer', {'correct_answer': _ca}, room=room_code)
                    await asyncio.sleep(2)
                # 🆕 نفس الحرف المختار: سؤال جديد لنفس الحرف (لا نعيد الاختيار)
                await sio.emit('huroof_timeout_info', {'msg': 'لم تتم الإجابة! سؤال جديد لنفس الحرف...'}, room=room_code)
                await asyncio.sleep(1)
                gs.state_version += 1
                await trigger_new_question(room_code, is_change=True)

    async def trigger_new_question(room_code, is_change=False):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'): return
        gs = room['game_state']
        gs.attempts = 1

        norm_letter = normalize_letter(gs.active_hex['letter'])

        # كل عمل DB صار في threads (asyncio.to_thread) — لا يحجب event loop:
        # 1) user_id يؤخذ من connected_players مباشرة (كان بحث session_token غير مفهرس)
        # 2) الأسئلة من الكاش (كان سحب الجدول كاملاً لكل سؤال)
        uids = []
        for player in room.get('players', []):
            p_sid = player.get('sid')
            if not p_sid:
                continue
            uid = connected_players.get(p_sid, {}).get('user_id')
            if uid:
                uids.append(uid)

        combined_seen = await asyncio.to_thread(_fetch_combined_seen, uids)
        all_qs = await asyncio.to_thread(_load_huroof_questions_cached)

        used = set(gs.used_questions) if hasattr(gs, 'used_questions') else set()
        # قائمة الحرف كاملةً (كل أسئلة هذا الحرف بغضّ النظر عن الرؤية)
        letter_qs = [
            q for q in all_qs
            if norm_letter in q.get('valid_letters', set())
        ]
        # ملاحظة: نعتمد على الحرف المحسوب من الإجابة (بعد إزالة ال)،
        # لا على extra.letter اليدوي في القاعدة — فقد يكون مصنّفاً خطأ
        # (مثل "البحرين" تحت الألف بدل الباء).
        valid_qs = [q for q in letter_qs
                    if q['id'] not in used and q['id'] not in combined_seen]

        # التدرّج حتى لا يبقى الحرف بلا سؤال أبداً (لكل الأنظمة):
        #   1) جديد غير مرئي  →  2) غير مستخدم بالمباراة (ولو رآه سابقاً)
        #   →  3) توليد AI جديد (يقلّل التكرار)  →  4) إعادة استخدام قديم
        source = 'fresh'
        if not valid_qs:
            valid_qs = [q for q in letter_qs if q['id'] not in used]
            source = 'seen_ok'

        # 3) توليد سؤال جديد بالـAI — نحاول حين تقلّ الأسئلة الجديدة،
        #    لتخفيف التكرار المزعج. نتخطّاه بصمت لو تعذّر (بلا إبطاء اللعبة).
        if not valid_qs:
            try:
                from app.infrastructure.ai_judge import generate_huroof_question
                gen = await generate_huroof_question(norm_letter, timeout=6.0)
            except Exception:
                gen = None
            if gen and gen.get('answer'):
                gs.current_question = {
                    'question': gen['question'], 'answer': gen['answer'],
                    'category': gen.get('category', 'مُولّد'),
                    'accepted_answers': gen.get('accepted_answers', []),
                    'difficulty': gen.get('difficulty', 'medium'),
                }
                gs.question_shown_at = time.time()
                asyncio.create_task(send_secret_to_mobile(
                    gs.current_question['question'], gs.current_question['answer']))
                version = advance_state(gs, 'question')
                gs.buzzed_player = None
                await sio.emit('huroof_new_question', {
                    'questionData': gs.current_question, 'round': 'r1',
                    'timer': 40, 'changed': is_change
                }, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 40, 'timeout_buzz_r1')
                if getattr(gs, 'is_solo', False) and 'consider_buzz' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['consider_buzz'], room_code, version, 40)
                return

        # 4) إعادة استخدام أي سؤال للحرف (الملاذ قبل الأخير)
        if not valid_qs:
            valid_qs = letter_qs[:]
            source = 'reused'
            if hasattr(gs, 'used_questions'):
                gs.used_questions = [qid for qid in gs.used_questions
                                     if qid not in {q['id'] for q in letter_qs}]

        if not valid_qs:
            # لا يوجد ولا سؤال واحد لهذا الحرف في القاعدة إطلاقاً (نادر جداً).
            # التوليد الفوري بالـAI ميزة مستقبلية؛ حالياً الملاذ الأخير:
            # نختار خلية أخرى تلقائياً بدل ترك الشاشة معلّقة.
            print(f" لا يوجد أي سؤال لحرف '{norm_letter}' في القاعدة. اختيار حرف آخر.")
            empties = [i for i, h in enumerate(gs.board)
                       if h.get('color') not in ('green', 'orange')]
            if empties:
                new_idx = random.choice(empties)
                gs.active_hex = gs.board[new_idx]
                await sio.emit('huroof_hex_locked',
                               {'hexIndex': new_idx, 'letter': gs.active_hex['letter']},
                               room=room_code)
                gs.state_version += 1
                await asyncio.sleep(0.5)
                await trigger_new_question(room_code, is_change=True)
            return

        # اختيار التصنيف: لو اللاعب صاحب الدور اختار تصنيفاً مسبقاً، نُفضّله
        pref_map = getattr(gs, 'preferred_category', None)
        turn_sid = gs.turn  # gs.turn هو sid اللاعب صاحب الدور مباشرة
        if pref_map and pref_map.get(turn_sid):
            wanted = pref_map.get(turn_sid)
            filtered = [q for q in valid_qs if q['category'] == wanted]
            if filtered:
                valid_qs = filtered
            pref_map.pop(turn_sid, None)

        chosen = random.choice(valid_qs)

        if hasattr(gs, 'used_questions'):
            gs.used_questions.append(chosen['id'])
            gs.used_answers.append(chosen['correct_answer'])

        # تسجيل المشاهدة fire-and-forget — لا نؤخر وصول السؤال للاعبين
        if uids:
            asyncio.create_task(asyncio.to_thread(_mark_seen_thread, uids, chosen['id']))

        gs.current_question = {
            "question": chosen['question_text'],
            "answer": chosen['correct_answer'],
            "accepted_answers": chosen['accepted_answers'],
            "category": chosen['category'],
            "letter": norm_letter
        }

        version = advance_state(gs, 'buzz_r1')
        gs.buzzed_player = None
        gs.skip_votes.clear()

        # ANTI-CHEAT: track when question was shown for reaction time validation
        gs.question_shown_at = time.time()

        asyncio.create_task(send_secret_to_mobile(gs.current_question['question'], gs.current_question['answer']))

        await sio.emit('huroof_new_question', {
            'questionData': gs.current_question,
            'round': 'r1',
            'timer': 40,
            'changed': is_change
        }, room=room_code)

        sio.start_background_task(huroof_timer_task, room_code, version, 40, 'timeout_buzz_r1')

        # الوضع الفردي: نُشعر البوت أن سؤالاً ظهر (نافذة 40ث) ليقرّر البزّ
        if getattr(gs, 'is_solo', False) and 'consider_buzz' in _SOLO_HOOKS:
            sio.start_background_task(_SOLO_HOOKS['consider_buzz'], room_code, version, 40)

    async def process_answer_result(room_code, is_correct, player_ans, result=None):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'): return
        gs = room['game_state']
        sid = gs.buzzed_player
        player_color = 'green' if sid == gs.p1 else 'orange'
        
        if is_correct:
            gs.active_hex['color'] = player_color
            await sio.emit('huroof_answer_result', {'correct': True, 'answer': player_ans, 'hexIndex': gs.active_hex['index'], 'color': player_color}, room=room_code)
            
            if gs.check_win(player_color):
                await asyncio.sleep(1.5) 
                room = get_room_state(room_code)
                
                if room:
                    gs.points[player_color] += 1
                    
                    if gs.points[player_color] >= gs.points_to_win_match:
                        winner_player = next((p for p in room['players'] if p['color'] == player_color), None)
                        loser_player = next((p for p in room['players'] if p['color'] != player_color), None)
                        loser_color = 'orange' if player_color == 'green' else 'green'

                        # معامل مكافحة التواطؤ من user_ids الغرفة
                        from app.domains.games.anti_collusion import get_reward_multiplier
                        uids = list((room.get('user_ids') or {}).values())
                        mult = get_reward_multiplier(uids[0], uids[1]) if len(uids) == 2 else 1.0

                        # في thread — لا يحجب event loop
                        await asyncio.to_thread(
                            record_match_result, winner_player, loser_player,
                            room.get('game_mode', 'huroof'), extra={
                                'winner_rounds': gs.points[player_color],
                                'loser_rounds':  gs.points[loser_color],
                                'collusion_multiplier': mult,
                                'friendly': room.get('type') == 'friendly',
                            })

                        # مباراة مكتملة بشرف للطرفين  تعافي السمعة
                        from app.domains.games.leaver_penalty import record_clean_match
                        for _uid in (room.get('user_ids') or {}).values():
                            record_clean_match(_uid)

                        await sio.emit('huroof_match_over', {
                            'winner': player_color,
                            'points': gs.points,
                            'reason': 'normal'
                        }, room=room_code)

                        await asyncio.sleep(2)  
                        room['state'] = 'finished'
                        if room.get('game_state'):
                            room['game_state'].state_version += 9999  
                        await return_players_to_lobby(sio, room)
                        if room_code in rooms:
                            del rooms[room_code]
                            print(f" تم حذف الغرفة {room_code} بعد انتهاء المباراة.")
                    
                    else:
                        gs.round_number += 1
                        
                        await sio.emit('huroof_round_over', {
                            'winner': player_color,
                            'points': gs.points,
                            'next_round': gs.round_number
                        }, room=room_code)
                        
                        await asyncio.sleep(3)
                        
                        gs.reset_round_state(starting_turn=player_color) 
                        
                        await sio.emit('huroof_board_init', {'board': gs.board}, room=room_code)
                        await sio.emit('huroof_new_round_started', {
                            'turn': gs.turn
                        }, room=room_code)

                        # الوضع الفردي: لو الدور الأول في الجولة للبوت، يبدأ
                        if getattr(gs, 'is_solo', False) and 'after_turn' in _SOLO_HOOKS:
                            sio.start_background_task(_SOLO_HOOKS['after_turn'], room_code)
            else:
                advance_state(gs, 'selecting')
                gs.turn = sid
                await asyncio.sleep(2) 
                await emit_turn_changed(room_code, gs, sid)
                
        else:
            # الإجابة الصحيحة تُكشف فقط عند انتهاء السؤال للطرفين
            # (لا تُكشف عند الخطأ الأول لأن الخصم لا يزال له محاولة)
            correct_answer = gs.current_question.get('answer', '')
            feedback = "إجابة خاطئة"
            if result and result.get('verdict') == 'maybe':
                feedback = "إجابة قريبة لكن غير دقيقة"

            # هل هذه المحاولة الأخيرة فعلاً؟ (answer_r4 = آخر المحاولات الأربع)
            # answer_r2 ليست نهائية: السؤال يكمل للفرصة الأخيرة (r3/r4)
            is_final_attempt = gs.stage == 'answer_r4'

            payload = {
                'correct': False,
                'answer': player_ans,
                'feedback': feedback,
                'hexIndex': gs.active_hex['index'],
            }
            if is_final_attempt:
                payload['correct_answer'] = correct_answer  # 🆕 تُكشف للطرفين الآن
            await sio.emit('huroof_answer_result', payload, room=room_code)
            await asyncio.sleep(1.5)
            
            if gs.stage == 'answer_r1':
                version = advance_state(gs, 'answer_r2')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 20, 'round': 'r2'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
                if getattr(gs, 'is_solo', False) and 'on_transfer' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['on_transfer'], room_code, version, 20)
                
            elif gs.stage == 'answer_r2':
                # نهاية المرحلة الأولى  الفرصة الأخيرة (نفس السؤال). لا نكشف الإجابة بعد.
                gs.attempts = 2
                version = advance_state(gs, 'question') 
                gs.buzzed_player = None
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code) 
                if getattr(gs, 'is_solo', False) and 'consider_buzz' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['consider_buzz'], room_code, version, 30)
                
            elif gs.stage == 'answer_r3':
                version = advance_state(gs, 'answer_r4')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 12, 'round': 'r4'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')
                if getattr(gs, 'is_solo', False) and 'on_transfer' in _SOLO_HOOKS:
                    sio.start_background_task(_SOLO_HOOKS['on_transfer'], room_code, version, 12)
                
            elif gs.stage == 'answer_r4':
                # 🆕 نكشف الإجابة للطرفين (كلاهما أخطأ في كل المحاولات)
                await sio.emit('huroof_reveal_answer', {'correct_answer': correct_answer}, room=room_code)
                await sio.emit('huroof_timeout_info', {'msg': 'كلاكما أخطأ! سؤال جديد لنفس الحرف...'}, room=room_code)
                await asyncio.sleep(2)
                # 🆕 نفس الحرف المختار: سؤال جديد لنفس الحرف (لا نعيد الاختيار)
                gs.state_version += 1
                await trigger_new_question(room_code, is_change=True)

    @sio.event
    async def huroof_select_hex(sid, data):
        room_code = data.get('roomCode')
        hex_index = data.get('hexIndex')
        
        room = get_room_state(room_code)
        if not room: return
        gs = room['game_state']
        
        # تحقق موحّد (BaseGame) + التحقق الموجود
        if not _action_allowed(gs, sid, 'select_hex'):
            return
        if gs.stage != 'selecting' or not is_players_turn(room, gs, sid):
            return 
            
        gs.active_hex = gs.board[hex_index]
        await sio.emit('huroof_hex_locked', {'hexIndex': hex_index, 'letter': gs.active_hex['letter']}, room=room_code)
        
        await trigger_new_question(room_code)

    @sio.event
    async def huroof_buzz(sid, data):
        # ANTI-CHEAT: payload safety
        payload_issue = check_payload_safety(data)
        if payload_issue:
            await report_violation(sid, sio, payload_issue, severity=Severity.HIGH)
            return

        # temp ban check
        if is_temp_banned(sid):
            return

        # rate limiting (لا أحد يضغط buzz أكثر من 5/ثانية بشري)
        rate_issue = check_action_rate(sid, 'huroof_buzz', max_per_second=5)
        if rate_issue:
            await report_violation(sid, sio, rate_issue, severity=Severity.HIGH)
            return

        room_code = data.get('roomCode')
        if not isinstance(room_code, str) or len(room_code) > 20:
            await report_violation(sid, sio, "invalid_room_code", severity=Severity.MEDIUM)
            return

        room = get_room_state(room_code)

        # ANTI-CHEAT: validate buzz state
        buzz_issue = validate_huroof_buzz(sid, room, connected_players)
        if buzz_issue:
            await report_violation(sid, sio, buzz_issue, severity=Severity.HIGH)
            return

        if not room or not room.get('game_state'): return
        gs = room['game_state']

        allowed_stages = ['question', 'buzz_r1', 'buzz_r3']
        if gs.stage not in allowed_stages:
            print(f" تجاهل الضغطة: المرحلة الحالية هي {gs.stage}")
            return

        # ANTI-CHEAT: human reaction time check
        question_shown_at = getattr(gs, 'question_shown_at', None)
        if question_shown_at:
            reaction_issue = check_human_reaction(sid, question_shown_at)
            if reaction_issue:
                await report_violation(sid, sio, reaction_issue, severity=Severity.HIGH)
                return

        gs.buzzed_player = sid
        if not hasattr(gs, 'attempts'): gs.attempts = 1

        if gs.attempts == 1:
            current_time = 15
            version = advance_state(gs, 'answer_r1')
            timeout_type = 'timeout_answer_r1'
        else:
            current_time = 12
            version = advance_state(gs, 'answer_r3')
            timeout_type = 'timeout_answer_r3'


        await sio.emit('huroof_buzzed', {'sid': sid, 'time': current_time}, room=room_code)
        sio.start_background_task(huroof_timer_task, room_code, version, current_time, timeout_type)

    @sio.event
    async def huroof_submit_answer(sid, data):
        # ANTI-CHEAT: payload safety (very important - answer is user input)
        payload_issue = check_payload_safety(data)
        if payload_issue:
            await report_violation(sid, sio, payload_issue, severity=Severity.HIGH)
            return

        if is_temp_banned(sid):
            return

        rate_issue = check_action_rate(sid, 'huroof_submit_answer', max_per_second=2)
        if rate_issue:
            await report_violation(sid, sio, rate_issue, severity=Severity.HIGH)
            return

        room_code = data.get('roomCode')
        if not isinstance(room_code, str) or len(room_code) > 20:
            return

        player_ans = html.escape(str(data.get('answer', '')).strip())

        # length limit on answer (no novels)
        if len(player_ans) > 200:
            await report_violation(sid, sio, f"oversized_answer:{len(player_ans)}",
                                    severity=Severity.MEDIUM)
            return

        room = get_room_state(room_code)
        if not room: return
        gs = room['game_state']

        # ANTI-CHEAT: validate answer state
        answer_issue = validate_huroof_answer(sid, room, gs.buzzed_player)
        if answer_issue:
            await report_violation(sid, sio, answer_issue, severity=Severity.HIGH)
            return

        if gs.stage not in ['answer_r1', 'answer_r2', 'answer_r3', 'answer_r4']: return
        if sid != gs.buzzed_player: return

        # الإرسال يلتزم: نبطل مؤقّت الإجابة فوراً (بالإصدار) —
        # يمنع انفجار المهلة أثناء تحكيم AI (≤2ث) ومعالجة النتيجة مرتين.
        gs.state_version += 1

        correct_ans = gs.current_question['answer']
        accepted_list = gs.current_question['accepted_answers']
        req_letter = gs.current_question['letter']

        # المعالج: Normalize  Fuzzy  Token analysis (فوري — يحل ~97%)
        result = check_answer(player_ans, correct_ans, accepted_list, req_letter)
        is_correct = result['verdict'] == 'accept'

        # الطبقة 4 (AI Judge) — فقط للحالات الحدّية النادرة 'maybe'
        # مع timeout صارم + تساهل افتراضي (لا يُبطئ اللعبة).
        if result.get('verdict') == 'maybe':
            try:
                from app.infrastructure.ai_judge import judge_answer
                judged = await judge_answer(
                    gs.current_question.get('text', '') or correct_ans,
                    correct_ans, player_ans, timeout=2.0
                )
                is_correct = judged.get('accept', True)
                result['ai_source'] = judged.get('source')
            except Exception:
                # أي خطأ  متساهل (نعطي اللاعب الفائدة عند الشك)
                is_correct = True

        await process_answer_result(room_code, is_correct, player_ans, result)

    @sio.event
    async def huroof_vote_skip(sid, data):
        room_code = data.get('roomCode')
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing': return
        gs = room['game_state']
        
        if gs.stage in ['buzz_r1', 'buzz_r3', 'question']:
            gs.skip_votes.add(sid)
            await sio.emit('huroof_skip_voted', {'sid': sid}, room=room_code)

            # الوضع الفردي: صوت اللاعب وحده يكفي (البوت "يوافق" فوراً)
            solo = getattr(gs, 'is_solo', False)
            if solo or len(gs.skip_votes) >= 2:
                # 🆕 نكشف الإجابة الصحيحة للطرفين قبل تغيير السؤال (اتفقا على التغيير)
                correct_answer = ''
                if gs.current_question:
                    correct_answer = gs.current_question.get('answer', '')
                if correct_answer:
                    await sio.emit('huroof_reveal_answer', {'correct_answer': correct_answer}, room=room_code)
                    await asyncio.sleep(2)
                await sio.emit('huroof_timeout_info', {'msg': 'جاري جلب سؤال جديد...'}, room=room_code)
                gs.skip_votes = set()
                gs.state_version += 1 
                await trigger_new_question(room_code, is_change=True)

    @sio.event
    async def huroof_use_help(sid, data):
        """ استخدام مساعدة. data: { roomCode, helpId }
        قواعد: المساعدة مُفعّلة + لم تُستخدم من قبل (مرة واحدة في المباراة) +
        اللاعب في الوضع الصحيح للمساعدة."""
        from app.domains.games.huroof.helps import is_valid_help, get_help

        room_code = data.get('roomCode')
        help_id = data.get('helpId')
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']

        # 1) المساعدة صالحة ومُفعّلة؟
        if not is_valid_help(help_id):
            await sio.emit('huroof_help_result', {'ok': False, 'msg': 'مساعدة غير متاحة'}, to=sid)
            return

        # 2) اللاعب جزء من المباراة؟
        if sid not in (gs.p1, gs.p2):
            return

        # نحصل على user_id ووضع التطوير (للمخزون)
        from app.domains.games.core_manager import _allow_same_ip
        dev_mode = _allow_same_ip()
        user_id = (room.get('user_ids') or {}).get(sid)
        if not user_id:
            # نحاول من كائن اللاعب
            _pl = next((p for p in room['players'] if p.get('sid') == sid), None)
            user_id = _pl.get('user_id') if _pl else None

        # 3) لم تُستخدم من قبل؟ (مرة واحدة في المباراة)
        used = gs.helps_used.setdefault(sid, set())
        if help_id in used:
            await sio.emit('huroof_help_result', {'ok': False, 'msg': 'استخدمت هذه المساعدة من قبل'}, to=sid)
            return

        # 🤖 الوضع الفردي: المساعدات لا تُخصم من مخزون اللاعب إطلاقاً.
        #    السولو تدريب لا مقامرة برصيدك؛ ولذلك تتجدّد كل مباراة فردية.
        #    (قيد "مرة واحدة لكل مباراة" يبقى ساري المفعول عبر gs.helps_used)
        _is_solo = bool(getattr(gs, 'is_solo', False))

        # 4) يملك المساعدة في مخزونه؟ (إلا في وضع التطوير أو الفردي)
        if not dev_mode and not _is_solo and user_id:
            from app.domains.wallet.help_inventory import get_quantity
            if get_quantity(user_id, help_id) <= 0:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا تملك هذه المساعدة — اشترها من المتجر'}, to=sid)
                return

        # 5)  بوابة التوقيت حسب نوع المساعدة:
        #    - "pre"  : تُستخدم قبل اختيار الحرف (في طور الاختيار فقط)
        #    - "post" : تتطلب حرفاً مختاراً وسؤالاً نشطاً
        #    - "any"  : مرنة، لكن تحتاج دور اللاعب نشطاً (مؤقّت)
        help_def = get_help(help_id)
        timing = (help_def or {}).get('timing', 'post')
        is_selecting = (gs.stage == 'selecting' or not gs.active_hex or not gs.current_question)

        if timing == 'pre':
            if not is_selecting:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'تُستخدم قبل اختيار الحرف'}, to=sid)
                return
        elif timing == 'post':
            if is_selecting:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'اختر حرفاً أولاً'}, to=sid)
                return
        else:  # any — مرنة: تحتاج فقط أن يكون الدور للاعب (مؤقّت نشط)
            at = getattr(gs, 'active_timer', None)
            if not at:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'انتظر دورك'}, to=sid)
                return

        # 5.5) ملكية الدور: في الأطوار التناوبية (اختيار الحرف والإجابة)
        #      المساعدة لصاحب الدور فقط — تمنع تخريب سؤال الخصم الحي
        #      (تغيير سؤاله/تخطي حرفه) وكشف حروف إجابته والعبث بمؤقّته.
        #      مراحل الجرس (buzz_r1/buzz_r3) سؤال مشترك يتنافس عليه
        #      الطرفان — تبقى المساعدات متاحة لكليهما فيها.
        if gs.stage not in ('buzz_r1', 'buzz_r3') and gs.turn != sid:
            await sio.emit('huroof_help_result', {'ok': False, 'msg': 'انتظر دورك'}, to=sid)
            return

        # نستهلك من المخزون (إلا في وضع التطوير أو الفردي) — قبل التنفيذ
        if not dev_mode and not _is_solo and user_id:
            from app.domains.wallet.help_inventory import consume_help
            if not consume_help(user_id, help_id):
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'نفد رصيدك من هذه المساعدة'}, to=sid)
                return

        # ===== تنفيذ كل مساعدة =====

        # ⏱ تمديد الوقت: نعيد تشغيل المؤقّت النشط بثوانٍ إضافية (خادمياً — فعّال حقاً)
        if help_id == 'extend_time':
            at = getattr(gs, 'active_timer', None)
            if not at or at.get('version') != gs.state_version:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا يوجد مؤقّت نشط الآن'}, to=sid)
                return
            extra = help_def['params'].get('seconds', 10)
            import time as _t
            remaining = max(0, at['ends_at'] - _t.time())
            new_seconds = int(remaining) + extra
            # نبدّل الإصدار لإلغاء المؤقّت القديم، ونشغّل واحداً جديداً بالوقت الممدّد
            gs.state_version += 1
            new_version = gs.state_version
            used.add(help_id)
            sio.start_background_task(huroof_timer_task, room_code, new_version,
                                     new_seconds, at['timeout_type'])
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'extend_time',
                'seconds': extra, 'new_total': new_seconds,
                'msg': f'تم تمديد وقتك +{extra} ثانية'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # تغيير السؤال: نجلب سؤالاً جديداً لنفس الحرف
        if help_id == 'change_question':
            if gs.stage not in ('buzz_r1', 'question') or not gs.active_hex:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا يمكن تغيير السؤال الآن'}, to=sid)
                return
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'change_question',
                'msg': 'جاري جلب سؤال جديد لنفس الحرف...'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            gs.state_version += 1
            await trigger_new_question(room_code, is_change=True)
            return

        # كاشف عدد الحروف: نحسب طول الإجابة ونرسله لصاحب المساعدة فقط
        if help_id == 'count_letters':
            if not gs.current_question:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا يوجد سؤال حالياً'}, to=sid)
                return
            answer = gs.current_question.get('answer', '') or ''
            # نحسب الحروف العربية فقط (نتجاهل المسافات)
            letter_count = len(answer.replace(' ', ''))
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'count_letters',
                'count': letter_count,
                'msg': f'عدد حروف الإجابة: {letter_count}'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # كاشف الحرف الثاني: الحرف الذي يلي المختار
        if help_id == 'reveal_second_letter':
            answer = (gs.current_question.get('answer', '') or '').replace(' ', '')
            if len(answer) < 2:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'الإجابة قصيرة جداً'}, to=sid)
                return
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'reveal',
                'msg': f'الحرف الثاني: {answer[1]}'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # كاشف آخر حرف
        if help_id == 'reveal_last_letter':
            answer = (gs.current_question.get('answer', '') or '').replace(' ', '')
            if not answer:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا توجد إجابة'}, to=sid)
                return
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'reveal',
                'msg': f'الحرف الأخير: {answer[-1]}'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # تلميح التصنيف
        if help_id == 'hint_category':
            cat = gs.current_question.get('category', '') or 'غير محدد'
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'reveal',
                'msg': f'تصنيف السؤال: {cat}'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # كاشف حرف وسطي: نكشف حرفاً واحداً من وسط الإجابة (تلميح خفيف)
        if help_id == 'reveal_middle_letter':
            answer = (gs.current_question.get('answer', '') or '').replace(' ', '')
            if not answer:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا توجد إجابة'}, to=sid)
                return
            mid = len(answer) // 2
            letter = answer[mid]
            # رقم الموضع للمستخدم (1-مبني)
            pos = mid + 1
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'reveal',
                'msg': f'الحرف رقم {pos} من الإجابة هو: {letter}'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # تجميد المؤقّت: نمدّد المؤقّت 5 ثوانٍ (نفس آلية تمديد الوقت)
        if help_id == 'freeze_timer':
            at = getattr(gs, 'active_timer', None)
            if not at or at.get('version') != gs.state_version:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا يوجد مؤقّت نشط'}, to=sid)
                return
            extra = help_def['params'].get('seconds', 5)
            import time as _t
            remaining = max(0, at['ends_at'] - _t.time())
            new_seconds = int(remaining) + extra
            gs.state_version += 1
            new_version = gs.state_version
            used.add(help_id)
            sio.start_background_task(huroof_timer_task, room_code, new_version,
                                     new_seconds, at['timeout_type'])
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'extend_time',
                'seconds': extra, 'new_total': new_seconds,
                'msg': f'تم تجميد المؤقّت +{extra} ثوانٍ'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # ⏭ تخطّي الحرف: نعيد اللاعب لاختيار حرف آخر (يلغي السؤال الحالي بلا عقوبة)
        if help_id == 'skip_letter':
            if gs.stage not in ('buzz_r1', 'question') or not gs.active_hex:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا يمكن التخطّي الآن'}, to=sid)
                return
            used.add(help_id)
            # نحرّر الخلية ونعيد مرحلة الاختيار لنفس اللاعب
            gs.active_hex = None
            gs.current_question = None
            gs.stage = 'selecting'
            gs.state_version += 1
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'skip_letter',
                'msg': 'تم تخطّي الحرف — اختر حرفاً آخر'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            # نُعلم الجميع بإلغاء السؤال والعودة للاختيار
            await sio.emit('huroof_skip_to_select', {'turn': gs.turn}, room=room_code)
            return

        # اختيار التصنيف (قبل الحرف): يحفظ تصنيفاً مفضّلاً لسؤالك القادم
        if help_id == 'choose_category':
            chosen_cat = (data.get('category') or '').strip()
            # قائمة التصنيفات المتاحة (من قاعدة الأسئلة)
            from app.domains.games.models import Question
            _db = SessionLocal()
            try:
                cats = [r[0] for r in _db.query(Question.category).filter(
                    Question.game_mode == 'huroof').distinct().all() if r[0]]
            except Exception:
                cats = []
            finally:
                _db.close()
            if not chosen_cat:
                # لم يحدّد بعد — نرسل له قائمة التصنيفات ليختار (لا نستهلك)
                await sio.emit('huroof_choose_category_options', {
                    'helpId': help_id, 'categories': cats,
                }, to=sid)
                # نُلغي الاستهلاك المبكر بإرجاع نسخة (تعويض)
                if not dev_mode and user_id:
                    from app.domains.wallet.help_inventory import add_help
                    add_help(user_id, help_id, 1)
                return
            if cats and chosen_cat not in cats:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'تصنيف غير متاح'}, to=sid)
                if not dev_mode and user_id:
                    from app.domains.wallet.help_inventory import add_help
                    add_help(user_id, help_id, 1)
                return
            # نحفظ التفضيل
            if not hasattr(gs, 'preferred_category'):
                gs.preferred_category = {}
            gs.preferred_category[sid] = chosen_cat
            used.add(help_id)
            await sio.emit('huroof_help_result', {
                'ok': True, 'helpId': help_id, 'effect': 'choose_category',
                'msg': f'سيكون سؤالك القادم من تصنيف: {chosen_cat}'
            }, to=sid)
            opp = gs.p2 if sid == gs.p1 else gs.p1
            await sio.emit('huroof_opponent_used_help', {'helpId': help_id, 'name': help_def['name']}, to=opp)
            return

        # المساعدات التي تحتاج دمجاً أعمق (second_chance) — مؤجّلة
        await sio.emit('huroof_help_result', {'ok': False, 'msg': 'هذه المساعدة قيد التطوير'}, to=sid)
        return

    @sio.event
    async def huroof_get_helps_catalog(sid, data):
        """يُرجع كتالوج المساعدات المُفعّلة + ما استُخدم + المخزون + عدد الخانات."""
        from app.domains.games.huroof.helps import (get_enabled_catalog, DEFAULT_LOADOUT,
                                             get_slots_for_player, FOURTH_SLOT_LEVEL, FOURTH_SLOT_ITEM)
        from app.domains.games.core_manager import _allow_same_ip
        room_code = (data or {}).get('roomCode')
        room = get_room_state(room_code)
        used_list = []
        inventory = {}
        dev_mode = _allow_same_ip()
        slots = 3
        player_level = 0
        _saved_loadout = None
        if room and room.get('game_state'):
            gs = room['game_state']
            used_list = list(gs.helps_used.get(sid, set()))
            user_id = (room.get('user_ids') or {}).get(sid)
            if not user_id:
                _pl = next((p for p in room['players'] if p.get('sid') == sid), None)
                user_id = _pl.get('user_id') if _pl else None
            if user_id:
                from app.domains.wallet.help_inventory import get_inventory, grant_starter_helps_once
                grant_starter_helps_once(user_id)  # هدية البداية للاعب الجديد
                inventory = get_inventory(user_id)
                # نجلب مستوى اللاعب لحساب الخانات
                try:
                    from app.domains.users.models import User
                    from app.infrastructure.database import SessionLocal
                    _db = SessionLocal()
                    _u = _db.query(User).filter(User.id == user_id).first()
                    player_level = (_u.level if _u else 0) or 0
                    _db.close()
                except Exception:
                    player_level = 0
                from app.domains.wallet.cosmetics import owns_cosmetic
                owns_fourth = owns_cosmetic(user_id, FOURTH_SLOT_ITEM)
                slots = get_slots_for_player(player_level, owns_fourth)
                try:
                    from app.domains.wallet.loadout import get_loadout
                    _saved_loadout = get_loadout(user_id, player_level)
                except Exception:
                    _saved_loadout = None
        # 🤖 الوضع الفردي: مخزون افتراضي كامل.
        #    السولو تدريب: لا يُخصم منك شيء، ومن ثمّ لا معنى لأن يمنعك
        #    رصيدٌ فارغ من تجربة مساعدة. نُظهر كل مساعدة مفعّلة برصيد 1
        #    على الأقل (الرصيد الحقيقي يبقى كما هو في قاعدة البيانات).
        #    وقيد "مرة واحدة لكل مباراة" يبقى سارياً عبر gs.helps_used،
        #    فيتجدّد تلقائياً في المباراة الفردية التالية.
        if room and room.get('game_state') and getattr(room['game_state'], 'is_solo', False):
            _inv = dict(inventory or {})
            for _h in get_enabled_catalog():
                _hid = _h.get('id')
                if _hid and int(_inv.get(_hid, 0)) < 1:
                    _inv[_hid] = 1
            inventory = _inv

        await sio.emit('huroof_helps_catalog', {
            'loadout': (_saved_loadout if _saved_loadout else DEFAULT_LOADOUT),
            'catalog': get_enabled_catalog(),
            'used': used_list,
            'inventory': inventory,
            'devMode': dev_mode,
            'slots': slots,
            'fourthSlotLevel': FOURTH_SLOT_LEVEL,
            'playerLevel': player_level,
        }, to=sid)

    @sio.event
    async def huroof_send_emoji(sid, data):
        """إرسال إيموجي متحرك. data: { roomCode, emojiId }
        يُبثّ للطرفين مع تحديد isMine لكل مستقبل."""
        room_code = (data or {}).get('roomCode')
        emoji_id = (data or {}).get('emojiId')
        if not emoji_id or not isinstance(emoji_id, str) or len(emoji_id) > 40:
            return
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if sid not in (gs.p1, gs.p2):
            return

        # معدّل الإرسال: نمنع السبام (إيموجي كل ثانية كحد)
        rate_issue = check_action_rate(sid, 'huroof_send_emoji', max_per_second=1)
        if rate_issue:
            return

        opp = gs.p2 if sid == gs.p1 else gs.p1
        # للمُرسِل: isMine=True
        await sio.emit('huroof_emoji', {'emojiId': emoji_id, 'isMine': True}, to=sid)
        # للخصم: isMine=False
        await sio.emit('huroof_emoji', {'emojiId': emoji_id, 'isMine': False}, to=opp)

    @sio.event
    async def huroof_get_my_emojis(sid, data):
        """يُرجع قائمة إيموجيات اللاعب المملوكة (الأساسية + المشتراة)."""
        room_code = (data or {}).get('roomCode')
        room = get_room_state(room_code)
        # الإيموجيات الأساسية المجانية (يملكها الجميع)
        base = ['emoji_laugh', 'emoji_cry', 'emoji_angry', 'emoji_think']
        owned = list(base)
        if room and room.get('game_state'):
            gs = room['game_state']
            user_id = (room.get('user_ids') or {}).get(sid)
            if not user_id:
                _pl = next((p for p in room['players'] if p.get('sid') == sid), None)
                user_id = _pl.get('user_id') if _pl else None
            if user_id:
                try:
                    from app.domains.wallet.cosmetics import get_owned_cosmetics
                    cosmetics = get_owned_cosmetics(user_id)
                    # نضيف الإيموجيات المشتراة (تبدأ بـ emoji_)
                    for c in cosmetics:
                        if c.startswith('emoji_') and c not in owned:
                            owned.append(c)
                except Exception:
                    pass
        await sio.emit('huroof_my_emojis', {'owned': owned}, to=sid)

    @sio.event
    async def huroof_surrender(sid, data):
        room_code = data.get('roomCode')
        room = get_room_state(room_code)
        
        if room:
            winner_color = 'orange' if room['players'][0]['sid'] == sid else 'green'
            
            loser_player = next((p for p in room['players'] if p['sid'] == sid), None)
            winner_player = next((p for p in room['players'] if p['sid'] != sid), None)
            from app.domains.games.anti_collusion import get_reward_multiplier
            uids = list((room.get('user_ids') or {}).values())
            mult = get_reward_multiplier(uids[0], uids[1]) if len(uids) == 2 else 1.0
            await asyncio.to_thread(
                record_match_result, winner_player, loser_player, room.get('game_mode', 'huroof'),
                extra={'reason': 'surrender', 'collusion_multiplier': mult,
                       'friendly': room.get('type') == 'friendly'})

            # عقوبة الانسحاب المتكرر (للمنسحب) + مكافأة الفائز (سلوك جيد)
            # المباريات الودية لا تُطبّق عقوبة انسحاب (صفر مخاطر)
            is_friendly = room.get('type') == 'friendly'
            user_ids_map = room.get('user_ids') or {}
            loser_uid = user_ids_map.get(sid)
            winner_uid = user_ids_map.get(winner_player['sid']) if winner_player else None
            from app.domains.games.leaver_penalty import record_leave, record_clean_match
            if loser_uid and not is_friendly:
                pen = record_leave(loser_uid)
                if pen['action'] != 'none':
                    await sio.emit('leaver_penalty', {'msg': pen['msg'], 'action': pen['action']}, to=sid)
            if winner_uid and not is_friendly:
                record_clean_match(winner_uid)

            await sio.emit('show_winner', {'color': winner_color, 'reason': 'surrender'}, room=room_code)
            
            room['state'] = 'finished'
            if room.get('game_state'):
                room['game_state'].state_version += 9999 
            
            await return_players_to_lobby(sio, room)
            
            if room_code in rooms:
                del rooms[room_code]
                print(f" تم حذف الغرفة {room_code} نهائياً من الذاكرة.")
        
    @sio.event
    async def join_party_mode(sid, data):
        # تم استيراد المتغيرات من ملف الحالة المركزية (سننشئه في الخطوة التالية)
        from app.sockets.state import connected_players, party_session_used_ids
        import app.sockets.state as state # للوصول للمتغيرات وتعديلها
        
        game_mode = data.get('gameMode', 'huroof')
        player_name = data.get('name', 'لاعب')
        avatar = data.get('avatar', 'https://api.dicebear.com/7.x/bottts/svg?seed=Hero')
        
        connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': f"party_{game_mode}"}

        if state.party_session_sid is None:
            state.party_session_sid = sid
            state.party_session_used_ids = set()
        
        # إصلاح أمني: كان يبث connected_players.values() خاماً — يسرّب token/user_id للجميع!
        # الآن delta منظّف (بدون حقول داخلية) عبر نظام الحضور.
        from app.domains.games.sockets.lobby import presence_delta
        await presence_delta(sio, sid, 'update')

    @sio.event
    async def request_ai_question(sid, data):
        from app.sockets.state import party_session_used_ids
        letter = data.get('letter', 'أ').strip()
        requested_category = data.get('category', 'عام')
        norm_letter = normalize_letter(letter)

        db = SessionLocal()
        try:
            query = db.query(Question).filter(Question.game_mode == "huroof")
            if requested_category != 'عام':
                query = query.filter(Question.category == requested_category)

            all_qs = query.all()

            # نبني قائمة الأسئلة المتاحة بعد استبعاد المستخدمة في هذه الجلسة
            valid = []
            for q in all_qs:
                if q.id in party_session_used_ids:
                    continue
                try:
                    ans = q.correct_answer.strip()
                    if ans.startswith("ال"):
                        ans = ans[2:]
                    extra = json.loads(q.extra_data) if q.extra_data else {}
                    letter_from_extra = normalize_letter(extra.get("letter", ""))
                    letter_from_ans = normalize_letter(ans[0]) if ans else ""
                    if letter_from_extra == norm_letter or letter_from_ans == norm_letter:
                        valid.append(q)
                except (json.JSONDecodeError, AttributeError, IndexError, TypeError):
                    pass

            if valid:
                chosen = random.choice(valid)
                # نحجز السؤال فوراً في سجل الجلسة قبل الإرسال
                party_session_used_ids.add(chosen.id)
                qa_data = {
                    "question": chosen.question_text,
                    "answer": chosen.correct_answer,
                    "category": chosen.category,
                    "letter": norm_letter
                }
                asyncio.create_task(send_secret_to_mobile(qa_data['question'], qa_data['answer']))
                await sio.emit('receive_ai_question', qa_data, to=sid)
            else:
                # نفدت كل أسئلة هذا الحرف في هذا التصنيف — نرسل رسالة للمستخدم
                print(f" [Party] نفدت أسئلة حرف '{norm_letter}' بتصنيف '{requested_category}'.")
                fallback = {
                    "question": f"عذراً، نفدت أسئلة حرف ({norm_letter}) في هذا التصنيف. جرب تصنيفاً آخر.",
                    "answer": "لا يوجد",
                    "category": "نفدت الأسئلة",
                    "letter": norm_letter,
                    "accepted_answers": []
                }
                await sio.emit('receive_ai_question', fallback, to=sid)
        finally:
            db.close()
    # ==========================================
    # الإبلاغ عن الخصم (أثناء/بعد المباراة)
    # ==========================================
    @sio.event
    async def report_opponent(sid, data):
        """
        بلاغ عن الخصم. يُحقّق الهوية عبر التوكن، ويحدّد الهدف من الغرفة إن توفّرت
        على هذا الـ worker، وإلا يعتمد target_id المرسل من الواجهة (يعمل مع تعدّد الـ workers).
        data: { roomCode, token, reason, target_id?, game_mode? }
        """
        data = data or {}
        room_code = data.get('roomCode')
        token = data.get('token')
        reason = data.get('reason', 'other')
        game_mode = data.get('game_mode')
        client_target = data.get('target_id')

        from app.sockets.auth_helper import verify_socket_token
        user, db = verify_socket_token(token)
        if not user:
            await sio.emit('report_result', {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
            return
        reporter_id = user.id
        db.close()

        # 1) نحاول التحديد من الغرفة (تحقّق أدق أنّ الهدف خصم فعلي) إن كانت متاحة هنا
        target_id = None
        room = get_room_state(room_code) if room_code else None
        if room:
            target = next((p for p in room['players'] if p['sid'] != sid), None)
            if target:
                target_id = target.get('user_id') or (room.get('user_ids') or {}).get(target['sid'])
            if not game_mode:
                game_mode = room.get('game_mode')

        # 2) fallback: هوية الخصم من الواجهة — تعمل عبر أي worker بلا اعتماد على الغرفة
        if not target_id and client_target is not None:
            try:
                target_id = int(client_target)
            except (TypeError, ValueError):
                target_id = None

        if not target_id:
            await sio.emit('report_result', {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
            return

        from app.domains.support.player_reports import submit_report
        result = submit_report(
            reporter_id=reporter_id,
            target_id=target_id,
            reason=reason,
            room_code=room_code,
            game_mode=game_mode or 'unknown',
        )
        await sio.emit('report_result', {'ok': result['ok'], 'msg': result['msg']}, to=sid)

    # ==========================================
    # الصداقة والحظر (من بروفايل الخصم)
    # ============================================================
    #  الوضع الفردي (اللعب ضد الكمبيوتر) — طبقة الربط
    # ------------------------------------------------------------
    #  معزولة تماماً: كل شيء محروس بـ gs.is_solo، فلا يمسّ الأونلاين.
    #  البوت لاعب وهمي (sid=__BOT__) بلا اتصال. حلقات خلفية تراقب
    #  المراحل وتتصرّف نيابةً عنه عبر نفس دوال اللعبة الداخلية.
    # ============================================================
    from app.domains.games.huroof import solo_bot as _solo

    async def _bot_take_turn_select(room_code):
        """دور البوت في الاختيار: يختار خلية ثم يعرض السؤال."""
        await asyncio.sleep(random.uniform(1.2, 2.5))
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing': return
        gs = room.get('game_state')
        if not gs or not getattr(gs, 'is_solo', False): return
        if gs.stage != 'selecting' or gs.turn != _solo.BOT_SID: return

        # لون البوت يُشتقّ من موضعه (p1=أخضر, p2=برتقالي) — نفس مصدر المحرّك
        # تماماً، فيستحيل أن يبني باتجاه لون آخر.
        bot_color = 'green' if _solo.BOT_SID == gs.p1 else 'orange'
        idx = _solo.choose_hex(gs.board, bot_color, gs.bot_difficulty)
        if idx is None: return
        gs.active_hex = gs.board[idx]
        await sio.emit('huroof_hex_locked',
                       {'hexIndex': idx, 'letter': gs.active_hex['letter']},
                       room=room_code)
        await trigger_new_question(room_code)

    async def _bot_consider_buzz(room_code, version, window_seconds):
        """عند ظهور سؤال: يقرّر البوت هل/متى يبزّ، وينفّذ إن لم يسبقه اللاعب."""
        room = get_room_state(room_code)
        if not room or not room.get('game_state'): return
        gs = room['game_state']
        if not getattr(gs, 'is_solo', False): return

        q = gs.current_question or {}
        qd = q.get('difficulty', 'medium')
        q_answer = q.get('answer', '')       # نثبّت إجابة *هذا* السؤال
        attempt = getattr(gs, 'attempts', 1)
        decision = _solo.decide_on_question(gs.bot_difficulty, qd, window_seconds, attempt)
        knows = decision['knows']            # محلّي — لا يُداس بحلقة أخرى

        if not decision['will_buzz']:
            return

        await asyncio.sleep(decision['delay'])

        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing': return
        gs = room.get('game_state')
        if not gs or gs.state_version != version: return
        if gs.stage not in ('question', 'buzz_r1', 'buzz_r3'): return
        if gs.buzzed_player is not None: return
        # حراسة إضافية: السؤال نفسه لم يتبدّل (يمنع البزّ على سؤال قديم)
        if (gs.current_question or {}).get('answer', '') != q_answer: return

        gs.buzzed_player = _solo.BOT_SID
        if getattr(gs, 'attempts', 1) == 1:
            t, new_stage, tt = 15, 'answer_r1', 'timeout_answer_r1'
        else:
            t, new_stage, tt = 12, 'answer_r3', 'timeout_answer_r3'
        v2 = advance_state(gs, new_stage)
        await sio.emit('huroof_buzzed', {'sid': _solo.BOT_SID, 'time': t}, room=room_code)
        sio.start_background_task(huroof_timer_task, room_code, v2, t, tt)

        await asyncio.sleep(random.uniform(1.5, 3.5))
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing': return
        gs = room.get('game_state')
        if not gs or gs.state_version != v2: return
        if gs.buzzed_player != _solo.BOT_SID: return
        # حراسة: نفس السؤال ما زال معروضاً
        if (gs.current_question or {}).get('answer', '') != q_answer: return

        gs.state_version += 1
        ans_text = q_answer if knows else '—'
        await process_answer_result(room_code, knows, ans_text)

    async def _solo_after_turn(room_code):
        """يُستدعى بعد تغيّر الدور: لو صار دور البوت، يبدأ اختياره."""
        room = get_room_state(room_code)
        if not room: return
        gs = room.get('game_state')
        if gs and getattr(gs, 'is_solo', False) and gs.turn == _solo.BOT_SID:
            sio.start_background_task(_bot_take_turn_select, room_code)

    async def _bot_answer_transfer(room_code, version, window_seconds):
        """الفرصة انتقلت للبوت (اللاعب أخطأ). البوت يجيب إن كان يعرف.
        لا بزّ هنا — الدور صار له مباشرة بنافذة window_seconds."""
        room = get_room_state(room_code)
        if not room or not room.get('game_state'): return
        gs = room['game_state']
        if not getattr(gs, 'is_solo', False): return
        if gs.buzzed_player != _solo.BOT_SID: return

        # هل يعرف؟ (المحاولة المنقولة عادةً attempt=1 لكن بعد خطأ الخصم)
        q = gs.current_question or {}
        knows = _solo.bot_knows_answer(gs.bot_difficulty, q.get('difficulty', 'medium'),
                                       getattr(gs, 'attempts', 1))
        # تأخير بشري ضمن النافذة (لا يستهلكها كلها)
        await asyncio.sleep(random.uniform(2.0, min(window_seconds * 0.7, 8.0)))

        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing': return
        gs = room.get('game_state')
        if not gs or gs.state_version != version: return
        if gs.buzzed_player != _solo.BOT_SID: return

        gs.state_version += 1
        ans_text = gs.current_question.get('answer', '') if knows else '—'
        await process_answer_result(room_code, knows, ans_text)

    async def _solo_on_transfer(room_code, version, window_seconds):
        """يُستدعى عند نقل الفرصة: لو المستلِم هو البوت، يردّ."""
        room = get_room_state(room_code)
        if not room: return
        gs = room.get('game_state')
        if gs and getattr(gs, 'is_solo', False) and gs.buzzed_player == _solo.BOT_SID:
            sio.start_background_task(_bot_answer_transfer, room_code, version, window_seconds)

    # نُتيح لـ trigger_new_question و emit_turn_changed إشعارَ البوت
    # عبر خطّافات مشتركة (تُملأ هنا، وتُقرأ هناك بأمان لو موجودة).
    _SOLO_HOOKS['consider_buzz'] = _bot_consider_buzz
    _SOLO_HOOKS['after_turn'] = _solo_after_turn
    _SOLO_HOOKS['on_transfer'] = _solo_on_transfer

    @sio.event
    async def huroof_start_solo(sid, data):
        """يبدأ مباراة فردية: لاعب حقيقي ضد البوت.
        data: { difficulty, token?, name?, avatar? }"""
        difficulty = (data or {}).get('difficulty', _solo.DEFAULT_DIFFICULTY)
        if difficulty not in _solo.DIFFICULTIES:
            difficulty = _solo.DEFAULT_DIFFICULTY

        # اللاعب قد يصل صفحة حروف مباشرة دون المرور باللوبي العام،
        # فلا يكون في connected_players بعد. نتحقّق من التوكن هنا ونسجّله.
        player = connected_players.get(sid)
        if not player:
            token = (data or {}).get('token')
            player_name = str((data or {}).get('name', 'لاعب'))[:30]
            avatar = (data or {}).get('avatar', '')
            user_id = None
            try:
                from app.sockets.auth_helper import verify_socket_token
                user, db = verify_socket_token(token)
                if user:
                    player_name = user.player_name or player_name
                    avatar = user.avatar or avatar
                    user_id = user.id
                    db.close()
            except Exception:
                pass
            player = {'name': player_name, 'avatar': avatar,
                      'user_id': user_id, 'token': token}
            connected_players[sid] = player

        human_color = random.choice(['green', 'orange'])
        bot_color = 'orange' if human_color == 'green' else 'green'

        alphabet = string.ascii_uppercase + string.digits
        room_code = 'S' + ''.join(secrets.choice(alphabet) for _ in range(5))

        p_human = {'sid': sid, 'name': player.get('name', 'لاعب'),
                   'avatar': player.get('avatar'), 'token': player.get('token'),
                   'user_id': player.get('user_id')}
        p_bot = {'sid': _solo.BOT_SID, 'name': _solo.BOT_NAME,
                 'avatar': 'assets/avatars/avatar_1.svg', 'token': None,
                 'user_id': None}

        p1, p2 = (p_human, p_bot) if human_color == 'green' else (p_bot, p_human)

        gs = HuroofGameState(p1['sid'], p2['sid'], room_code=room_code,
                             players=[p1, p2])
        gs.is_solo = True
        gs.bot_difficulty = difficulty
        gs.bot_color = bot_color
        gs.bot_knows_current = False

        rooms[room_code] = {
            'code': room_code, 'type': 'solo', 'game_mode': 'huroof',
            'state': 'playing', 'created_at': time.time(), 'is_solo': True,
            'players': [
                {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'],
                 'user_id': p1.get('user_id'), 'color': 'green',
                 'role': 'host' if p1['sid'] == sid else 'bot'},
                {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'],
                 'user_id': p2.get('user_id'), 'color': 'orange',
                 'role': 'host' if p2['sid'] == sid else 'bot'},
            ],
            'user_ids': {},          # فارغ عمداً: لا تصنيف في الفردي
            'game_state': gs,
        }
        await sio.enter_room(sid, room_code)

        await sio.emit('solo_started', {
            'room_code': room_code, 'your_color': human_color,
            'bot_color': bot_color, 'difficulty': difficulty,
            'difficulty_label': _solo.get_difficulty(difficulty)['label'],
        }, to=sid)

        # نبني room_joined بنفس بنية الأونلاين — الواجهة تقرأ اللون
        # وإحصائيات اللاعبين من هذا الحدث (players[].color + .stats).
        try:
            from app.domains.wallet.reward_service import get_player_full_stats
            my_stats = await get_player_full_stats(player.get('token'),
                                                   player.get('name', 'لاعب'),
                                                   player.get('avatar', ''))
        except Exception:
            my_stats = {'name': player.get('name', 'لاعب'),
                        'avatar': player.get('avatar', ''), 'wins': 0, 'losses': 0}

        bot_stats = {'name': _solo.BOT_NAME, 'avatar': 'assets/avatars/avatar_1.svg',
                     'flag': '../assets/flags/EARTH.svg',
                     'wins': 0, 'losses': 0, 'elo': 0, 'rank_label': _solo.get_difficulty(difficulty)['label']}

        def _pub(p, color, stats):
            return {'sid': p['sid'], 'name': p['name'], 'avatar': p.get('avatar'),
                    'color': color, 'stats': stats,
                    'role': 'host' if p['sid'] == sid else 'bot'}

        if human_color == 'green':
            players_pub = [_pub(p1, 'green', my_stats), _pub(p2, 'orange', bot_stats)]
        else:
            players_pub = [_pub(p1, 'green', bot_stats), _pub(p2, 'orange', my_stats)]

        await sio.emit('room_joined', {
            'code': room_code, 'game_mode': 'huroof', 'state': 'playing',
            'is_solo': True, 'players': players_pub, 'your_sid': sid,
            'opponent_relation': 'none', 'opponent_user_id': None,
        }, to=sid)
        await sio.emit('update_players_stats', players_pub, to=sid)

        # نطابق تسلسل بدء الأونلاين: board_init ثم turn_changed
        await sio.emit('huroof_board_init', {'board': gs.board}, room=room_code)
        await sio.emit('huroof_turn_changed', {
            'turn_sid': gs.turn,
            'turn_color': ('green' if gs.turn == gs.p1 else 'orange')
        }, room=room_code)

        # لو الدور الأول للبوت، يبدأ اختياره
        await _solo_after_turn(room_code)

    # ==========================================
    # الصداقة والحظر (من بروفايل الخصم) — عبر الوحدة المشتركة
    from app.domains.games.sockets.social_handlers import register_social_handlers
    register_social_handlers(sio, get_room_state)