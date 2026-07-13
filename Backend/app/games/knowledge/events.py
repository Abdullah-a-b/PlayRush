"""
🧠 أحداث "ماذا تعرف" — Socket.IO (نسخة الأدوار والقوائم)

الدروس المدمجة:
- تحميل الأسئلة والتطبيع مرة واحدة بالذاكرة (كاش) — صفر DB بالمسار الساخن.
- صندوق الكتابة يظهر لصاحب الدور فقط، وبسرعة: العميل يعرضه فور
  knowledge_turn محلياً (لا رحلة إضافية).
- سباق المهلة×التحكيم: الإرسال يبطل مؤقت الدور فوراً (bump)، وعلم
  judging يمنع مهلة متأخرة من ضرب سترايك أثناء حكم AI.
- المكرر داخل الجولة = خطأ مباشر (سترايك) برسالة واضحة.
- الانسحاب: المنسحب 0 مكافآت وخصمه فوز كامل (reward_service يطبقها).
"""
import asyncio
import json
import os
import time

from app.games.core_manager import get_room_state, rooms
from app.services.reward_service import record_match_result
from app.core.text_processor import normalize_arabic

_sio_ref = None
_start_round_ref = None

# ==========================================================
# 📚 كاش أسئلة القوائم (تُحمَّل وتُطبَّع مرة واحدة)
# ==========================================================
_QCACHE = {'loaded': False, 'questions': []}
_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), 'data', 'knowledge_questions.json')


def _norm(t):
    try:
        return normalize_arabic(t or "")
    except Exception:
        return (t or '').strip()


def _load_questions():
    """يحمّل أسئلة القوائم + سؤال السور (من قائمة SURAHS المدققة)."""
    if _QCACHE['loaded']:
        return _QCACHE['questions']
    out = []
    try:
        with open(_DATA_FILE, encoding='utf-8') as f:
            raw = json.load(f).get('questions', [])
        for q in raw:
            pool = []
            for entry in q.get('answers', []):
                variants = [v.strip() for v in str(entry).split('|') if v.strip()]
                if not variants:
                    continue
                pool.append({'display': variants[0],
                             'norm': {_norm(v) for v in variants}})
            if len(pool) >= 15:
                out.append({'id': q['id'], 'q': q['q'],
                            'cat': q.get('cat', 'عام'), 'pool': pool})
    except Exception as e:
        print(f"⚠️ [knowledge] تحميل الأسئلة: {e}")
    # 📖 سؤال السور — يُبنى من القائمة المنسّقة نفسها (مصدر واحد للحقيقة)
    try:
        import sys
        scripts = os.path.join(os.path.dirname(_DATA_FILE), '..', 'scripts')
        scripts = os.path.abspath(scripts)
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from huroof_questions_import import SURAHS
        pool = [{'display': s, 'norm': {_norm(s), _norm('سورة ' + s)}}
                for s in SURAHS]
        out.append({'id': 'kq_surahs', 'q': 'اذكر سوراً من القرآن الكريم',
                    'cat': 'دين', 'pool': pool})
    except Exception as e:
        print(f"⚠️ [knowledge] سؤال السور غير متاح: {e}")
    _QCACHE['questions'] = out
    _QCACHE['loaded'] = True
    print(f"🧠 [knowledge] حُمّل {len(out)} سؤال قائمة "
          f"(أكبر قائمة {max((len(x['pool']) for x in out), default=0)} إجابة)")
    return out


# ---------- عدم تكرار الأسئلة عبر المباريات (شخصي لكل مستخدم، نمط البنك) ----------
def _seen_qids_for_user(user_id):
    """أسئلة سبق أن شاهدها هذا المستخدم (فلترة شخصية)."""
    if not user_id:
        return set()
    try:
        from app.core.database import SessionLocal
        from app.models.user import KnowledgeSeen
        db = SessionLocal()
        try:
            rows = db.query(KnowledgeSeen.question_id).filter(
                KnowledgeSeen.user_id == user_id).all()
            return {qid for (qid,) in rows}
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [knowledge] seen fetch: {e}")
        return set()


def _record_seen_bulk(user_id, question_ids):
    """يسجّل أسئلة المباراة دفعةً (fire-and-forget عند النهاية، في thread)."""
    if not user_id or not question_ids:
        return
    try:
        from app.core.database import SessionLocal
        from app.models.user import KnowledgeSeen
        db = SessionLocal()
        try:
            existing = {qid for (qid,) in db.query(KnowledgeSeen.question_id).filter(
                KnowledgeSeen.user_id == user_id,
                KnowledgeSeen.question_id.in_(list(question_ids))).all()}
            for qid in question_ids:
                if qid not in existing:
                    db.add(KnowledgeSeen(user_id=user_id, question_id=qid))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [knowledge] seen bulk: {e}")


def _recycle_seen(user_id):
    """نفدت الأسئلة لهذا المستخدم → نحذف أقدم نصف مشاهداته ليعيد رؤيتها."""
    if not user_id:
        return
    try:
        from app.core.database import SessionLocal
        from app.models.user import KnowledgeSeen
        db = SessionLocal()
        try:
            rows = db.query(KnowledgeSeen).filter(
                KnowledgeSeen.user_id == user_id).order_by(
                KnowledgeSeen.seen_at.asc()).all()
            for r in rows[: max(1, len(rows) // 2)]:
                db.delete(r)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [knowledge] seen recycle: {e}")


def _pick_question(used_ids, uid1=None, uid2=None):
    """يختار سؤالاً غير مكرّر: بالمباراة (used_ids) + مشاهدات الطرفين.
    عند النفاد يعيد التدوير. الفلترة تستبعد ما شاهده أيّ طرف (عدالة)."""
    import random
    seen = _seen_qids_for_user(uid1) | _seen_qids_for_user(uid2)
    blocked = set(used_ids) | seen
    qs = [q for q in _load_questions() if q['id'] not in blocked]
    if not qs and (uid1 or uid2):
        # نفدت لهذين المستخدمين → تدوير ثم إعادة
        _recycle_seen(uid1); _recycle_seen(uid2)
        seen = _seen_qids_for_user(uid1) | _seen_qids_for_user(uid2)
        blocked = set(used_ids) | seen
        qs = [q for q in _load_questions() if q['id'] not in blocked]
    if not qs:  # ملاذ أخير: بالمباراة فقط
        qs = [q for q in _load_questions() if q['id'] not in set(used_ids)]
    if not qs:
        qs = _load_questions()
    return random.choice(qs) if qs else None


async def trigger_knowledge_start(sio, room_code):
    """يبدأ المباراة (من room_events عند اكتمال الطرفين)."""
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        return
    gs = room['game_state']
    if gs.stage != 'waiting':
        return
    gs.stage = 'starting'
    import random
    gs.first_turn_round = random.choice([gs.p1, gs.p2])  # 🎲 البادئ عشوائي
    await asyncio.sleep(3.2)  # ⏳ أنيميشن "استعد 3-2-1"
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        return
    if _start_round_ref:
        await _start_round_ref(room_code)


def register_knowledge_events(sio):
    global _sio_ref, _start_round_ref
    _sio_ref = sio

    def _room_gs(room_code):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return None, None
        gs = room['game_state']
        # 🔑 مزامنة sids المحرك بلاعبي الغرفة في كل وصول — الجذر الأمتن
        # للمشكلتين: gs.p1/p2/turn قد تحمل sids قديمة (طابور/reconnect)
        # بينما الغرفة تحمل الحالية. نطابق عبر user_id (المعرّف الثابت).
        try:
            players = room.get('players', [])
            if len(players) == 2 and hasattr(gs, 'remap_sid'):
                for slot, uid_attr in (('p1', 'p1_uid'), ('p2', 'p2_uid')):
                    cur = getattr(gs, slot, None)
                    uid = getattr(gs, uid_attr, None)
                    if cur is None:
                        continue
                    rp = next((p for p in players if p.get('user_id') == uid), None) if uid else None
                    if rp is None:
                        idx = 0 if slot == 'p1' else 1
                        rp = players[idx]
                    new_sid = rp.get('sid')
                    if new_sid and new_sid != cur:
                        gs.remap_sid(cur, new_sid)
        except Exception as _e:
            print(f"⚠️ [knowledge] مزامنة sid: {_e}")
        return room, gs

    def _name_of(room, sid):
        p = next((p for p in room.get('players', []) if p.get('sid') == sid), None)
        return p.get('name', 'لاعب') if p else 'لاعب'

    # ---------- دورة الجولة ----------
    async def _start_round(room_code):
        room, gs = _room_gs(room_code)
        if not room or gs.stage == 'finished':
            return
        # 🚫 عدم التكرار: بالمباراة (used_question_ids) + مشاهدات الطرفين
        # (شخصي لكل مستخدم عبر المباريات، نمط البنك). في thread لأن فيه DB.
        _u1 = getattr(gs, 'p1_uid', None)
        _u2 = getattr(gs, 'p2_uid', None)
        q = await asyncio.to_thread(_pick_question, gs.used_question_ids, _u1, _u2)
        if not q:
            import random
            q = random.choice(_load_questions())
        # 🔁 تناوب البادئ بين الجولات (الجولة 1 حُسمت عشوائياً بالبداية)
        starter = gs.first_turn_round if gs.round_index == 0 else \
            gs.opponent(gs.first_turn_round)
        pool = [{'display': it['display'], 'norm': set(it['norm'])}
                for it in q['pool']]
        gs.begin_round({'id': q['id'], 'q': q['q'], 'cat': q['cat']}, pool, starter)
        gs.first_turn_round = starter
        is_tb = gs.round_index > gs.TOTAL_ROUNDS
        await _sio_ref.emit('knowledge_round_start', {
            'index': gs.round_index, 'total': gs.TOTAL_ROUNDS,
            'tiebreak': is_tb, 'q': q['q'], 'category': q['cat'],
            'pool_size': len(pool),
        }, room=room_code)
        await asyncio.sleep(1.2)  # لحظة قراءة السؤال
        await _begin_turn(room_code, starter)

    async def _begin_turn(room_code, sid):
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'turn':
            return
        # 🔑 الجذر النهائي: الـsid الوارد قد يكون sid محرك قديم (من
        # starter/opponent قبل مزامنة _room_gs). نترجمه لـsid الغرفة
        # الحالي عبر user_id — وإلا knowledge_turn يحمل sid قديماً لا
        # يطابق your_sid بالواجهة → iAmActive=false → كل إجابة سترايك.
        players = room.get('players', [])
        if sid not in (p.get('sid') for p in players):
            # نحدد أي slot، ثم نأخذ sid الغرفة الحالي لصاحب نفس user_id
            uid = gs.p1_uid if sid == gs.p1 else (gs.p2_uid if sid == gs.p2 else None)
            rp = next((p for p in players if p.get('user_id') == uid), None) if uid else None
            if rp is None and len(players) == 2:
                rp = players[0] if sid == gs.p1 else players[1]
            if rp and rp.get('sid'):
                sid = rp['sid']
        version = gs.begin_turn(sid)
        # ⚡ حدث واحد للجميع: صاحب الدور يفتح صندوقه محلياً فوراً
        # 🕐 نرسل turn_ends_at (Unix timestamp من الـ server) ليحسب الـ frontend
        # الوقت المتبقي بدقة بدلاً من بدء عداد محلي — يلغي تأثير تأخر الشبكة
        turn_ends_at = time.time() + gs.TURN_SECONDS
        await _sio_ref.emit('knowledge_turn', {
            'sid': sid, 'name': _name_of(room, sid),
            'seconds': gs.TURN_SECONDS,
            'turn_ends_at': turn_ends_at,
            'strikes': gs.strikes, 'points': gs.points,
        }, room=room_code)
        sio.start_background_task(_turn_timeout, room_code, version)

    async def _turn_timeout(room_code, version):
        room, gs = _room_gs(room_code)
        if not room:
            return
        # ⏱️ GRACE_BUFFER يمنع سترايك ظالم لإجابات وصلت في آخر لحظة (network lag)
        await asyncio.sleep(gs.TURN_SECONDS + gs.GRACE_BUFFER)
        room, gs = _room_gs(room_code)
        # ✅ الحارس: الإصدار. لو تغيّر فالدور تقدّم (إجابة/دور جديد) → نخرج.
        if not room or gs.state_version != version or gs.stage != 'turn':
            return
        # 🛑 إجابة قيد المعالجة (judging=True)؟ نخرج نهائياً — لا نكسرها
        # ولا نضرب سترايك. مسار الإجابة (بما فيه AI) هو من يحسم، بلا
        # ضغط وقت. هذا يمنع "انتهى الوقت وسترايك" بينما AI يفكّر.
        if gs.judging:
            return
        # ⏱️ انتهى العدّاد فعلاً بلا أي إجابة → سترايك مهلة + نقل الدور
        await _apply_strike(room_code, gs.turn, 'timeout', None)

    async def _apply_strike(room_code, sid, reason, echo_answer):
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'turn':
            return
        count = gs.add_strike(sid)
        await _sio_ref.emit('knowledge_strike', {
            'sid': sid, 'name': _name_of(room, sid),
            'count': count, 'max': gs.MAX_STRIKES,
            'reason': reason,            # wrong | timeout | repeat
            'answer': echo_answer or '',
            'strikes': gs.strikes,
        }, room=room_code)
        if count >= gs.MAX_STRIKES:
            await _close_round(room_code, loser_sid=sid)
        else:
            await asyncio.sleep(0.9)
            await _begin_turn(room_code, gs.opponent(sid))

    async def _on_correct(room_code, sid, display):
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'turn':
            return
        await _sio_ref.emit('knowledge_correct', {
            'sid': sid, 'name': _name_of(room, sid),
            'answer': display,
            'used': len(gs.used_answer_idx), 'pool': len(gs.answers_pool),
        }, room=room_code)
        if gs.pool_exhausted():
            await _close_round(room_code, loser_sid=None)  # 🕳️ نفدت القائمة
            return
        await asyncio.sleep(0.9)
        await _begin_turn(room_code, gs.opponent(sid))

    async def _close_round(room_code, loser_sid):
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'turn':
            return
        gains = gs.close_round(loser_sid)
        await _sio_ref.emit('knowledge_round_over', {
            'index': gs.round_index,
            'loser_sid': loser_sid,
            'loser_name': _name_of(room, loser_sid) if loser_sid else None,
            'exhausted': loser_sid is None,
            'gains': gains, 'points': gs.points, 'strikes': gs.strikes,
        }, room=room_code)
        if gs.is_over():
            await asyncio.sleep(gs.BETWEEN_SECONDS)
            await _finish(room_code)
            return
        if gs.round_index >= gs.TOTAL_ROUNDS:
            gs.tiebreak += 1  # 🔥 حسم إضافي عند التعادل
            await _sio_ref.emit('knowledge_tiebreak', {'round': gs.tiebreak}, room=room_code)
        await asyncio.sleep(gs.BETWEEN_SECONDS)
        gs.stage = 'turn'  # يسمح لبدء جولة جديدة
        await _start_round(room_code)

    async def _finish(room_code, surrender_by=None):
        room, gs = _room_gs(room_code)
        if not room or gs.stage == 'finished':
            return
        if surrender_by:
            gs.winner = gs.opponent(surrender_by)
            gs.stage = 'finished'
            gs.bump_version()
        else:
            gs.decide_winner()
        room['state'] = 'finished'
        winner_sid = gs.winner
        # 🔑 الجذر: gs.winner (sid المحرك) قد لا يطابق sid الغرفة (تغيّر
        # عبر join/reconnect). لو الطباق المباشر فشل، نستنتج بالاستبعاد
        # عبر p1/p2 — وإلا wp/lp=None → record_match_result لا يُستدعى →
        # البروفايل 0 مباريات.
        players = room['players']
        wp = next((p for p in players if p['sid'] == winner_sid), None)
        if wp is None and len(players) == 2:
            # نطابق عبر ترتيب p1/p2 بالمحرك
            loser_engine_sid = gs.p1 if winner_sid == gs.p2 else gs.p2
            wp = next((p for p in players if p['sid'] != loser_engine_sid), None)
            if wp is None:
                wp = players[0]  # ملاذ أخير: لا نفقد التسجيل
        lp = next((p for p in players if p is not wp), None)
        if wp and lp:
            try:
                extra = {'winner_score': gs.points.get(winner_sid, 0),
                         'loser_score': gs.points.get(lp['sid'], 0),
                         'friendly': room.get('type') == 'friendly'}
                if surrender_by:
                    extra['reason'] = 'surrender'  # المنسحب 0 — خصمه فوز كامل
                await asyncio.to_thread(record_match_result, wp, lp, 'knowledge', extra=extra)
            except Exception as e:
                print(f"⚠️ [knowledge] تسجيل: {e}")
        else:
            print(f"⚠️ [knowledge] تعذّر تحديد الفائز/الخاسر — لم تُسجّل "
                  f"(winner_sid={winner_sid} players={[p['sid'] for p in players]})")
        # 🚫 نسجّل أسئلة هذه المباراة كـ"مُشاهَدة" لكل لاعب (منع التكرار مستقبلاً)
        _qids = list(gs.used_question_ids)
        for _p in players:
            _uid = _p.get('user_id')
            if _uid and _qids:
                asyncio.create_task(asyncio.to_thread(_record_seen_bulk, _uid, _qids))
        await _sio_ref.emit('knowledge_match_over', {
            'winner_sid': winner_sid,
            'winner_name': _name_of(room, winner_sid),
            'points': gs.points,
            'reason': 'surrender' if surrender_by else 'normal',
        }, room=room_code)
        if room_code in rooms:
            from app.sockets.lobby import return_players_to_lobby
            await return_players_to_lobby(_sio_ref, room)
            del rooms[room_code]

    # ---------- أحداث اللاعبين ----------
    @sio.event
    async def knowledge_submit_answer(sid, data):
        room_code = (data or {}).get('roomCode')
        room, gs = _room_gs(room_code)
        if not room:
            return
        answer = str((data or {}).get('answer', '')).strip()[:60]
        if not answer:
            return
        # 🔑 الجذر النهائي: قد يصل sid الاتصال مختلفاً عن gs.turn لو انزاح
        # (إعادة اتصال Socket.IO تلقائية، polling↔ws). نطابق المُرسِل بلاعب
        # الغرفة، فإن كان هو صاحب الدور (نفس user_id) نصحّح sid ونقبل —
        # بدل رفض صامت يؤدي لمهلة+سترايك رغم أن الإجابة وصلت صحيحة.
        sender = next((p for p in room.get('players', []) if p.get('sid') == sid), None)
        if sender is None:
            return  # ليس لاعباً في هذه الغرفة
        turn_uid = gs.p1_uid if gs.turn == gs.p1 else (gs.p2_uid if gs.turn == gs.p2 else None)
        if turn_uid is not None and sender.get('user_id') == turn_uid and gs.turn != sid:
            # صاحب الدور لكن sid انزاح → نصحّح sid المحرك للمُرسِل
            if hasattr(gs, 'remap_sid'):
                gs.remap_sid(gs.turn, sid)
        if not gs.can_submit(sid):
            return
        # 🛡️ الإرسال يلتزم: يبطل مؤقّت الدور فوراً + قفل التحكيم
        gs.judging = True
        gs.bump_version()

        verdict, idx = gs.match_answer(_norm(answer))
        if verdict == 'correct':
            gs.consume_answer(idx)
            gs.judging = False
            await _on_correct(room_code, sid, gs.answers_pool[idx]['display'])
            return
        if verdict == 'repeat':
            gs.judging = False
            await _apply_strike(room_code, sid, 'repeat',
                                gs.answers_pool[idx]['display'])
            return
        # ⚖️ ليست بالقائمة حرفياً — سلسلة محسّنة لأسئلة القوائم:
        # القائمة معروفة ومحدودة، فالتشابه العالي معها موثوق (لا نحتاج AI).
        # 1) fuzzy ≥0.85 مع مرشح غير مستهلك → قبول مباشر (تنويع/خطأ إملائي)
        # 2) 0.72-0.85 → AI Judge إن توفّر مفتاح؛ وبلا مفتاح نثق بالتشابه
        #    (lenient_default هنا = قبول، لأن المرشح من قائمة صحيحة أصلاً)
        # 3) أقل من 0.72 → خطأ مباشر
        from app.core.text_processor import similarity_ratio
        n_ans = _norm(answer)
        best_idx, best_ratio = None, 0.0
        for i, item in enumerate(gs.answers_pool):
            if i in gs.used_answer_idx:
                continue
            for v in item['norm']:
                r = similarity_ratio(n_ans, v)
                if r > best_ratio:
                    best_ratio, best_idx = r, i
                # ✅ مطابقة بعد حذف/إضافة "ال" التعريف (برتغال=البرتغال، نمسا=النمسا)
                v_no_al = v[2:] if v.startswith('ال') else v
                n_no_al = n_ans[2:] if n_ans.startswith('ال') else n_ans
                if n_ans == v_no_al or n_no_al == v:
                    best_ratio, best_idx = 1.0, i
                    break
            if best_ratio >= 1.0:
                break
        is_correct = False
        used_ai = False
        try:
            if best_idx is not None and best_ratio >= 0.80:
                # تشابه عالٍ مع عنصر قائمة صحيح → قبول فوري (لا AI)
                is_correct = True
            elif best_idx is not None and best_ratio >= 0.62:
                # نطاق حدّي فقط → AI إن توفّر مفتاح؛ بلا مفتاح نثق بالتشابه
                used_ai = True
                await sio.emit('knowledge_judging', {'sid': sid}, room=room_code)
                from app.core.ai_judge import judge_answer
                judged = await judge_answer(
                    (gs.current_q or {}).get('q', ''),
                    gs.answers_pool[best_idx]['display'], answer, timeout=2.0)
                # المرشح من قائمة صحيحة، فحتى lenient (بلا مفتاح) مقبول
                is_correct = bool(judged.get('accept', False))
        except Exception:
            is_correct = (best_idx is not None and best_ratio >= 0.70)
        finally:
            gs.judging = False  # 🛡️ لا يتسرّب أبداً مهما حدث
        if gs.stage != 'turn' or gs.turn != sid:
            return  # الجولة تقدمت أثناء الحكم (المهلة سبقتنا) — نتركها لها
        if is_correct and best_idx is not None:
            gs.consume_answer(best_idx)
            await _on_correct(room_code, sid, gs.answers_pool[best_idx]['display'])
        else:
            await _apply_strike(room_code, sid, 'wrong', answer)

    @sio.event
    async def knowledge_surrender(sid, data):
        room_code = (data or {}).get('roomCode')
        room, gs = _room_gs(room_code)
        if not room or gs.stage == 'finished':
            return
        # 🛡️ نتحقق من لاعبي الغرفة مباشرة (مصدر الحقيقة) لا قائمة المحرك
        # المخزّنة — تفادياً لفشل الانسحاب لو تغيّر sid بعد reconnect
        in_room = any(p.get('sid') == sid for p in room.get('players', []))
        if not in_room:
            return
        # نضمن أن المحرك يعرف هذا الـ sid (لو تغيّر ولم يُعَد ربطه)
        if sid not in (gs.p1, gs.p2):
            # نربطه بمكان اللاعب في الغرفة
            players = room.get('players', [])
            if len(players) >= 2:
                # نطابق بالاسم/الترتيب: أول لاعب=p1، ثاني=p2
                idx = next((i for i, p in enumerate(players) if p.get('sid') == sid), None)
                if idx == 0 and hasattr(gs, 'remap_sid'):
                    gs.remap_sid(gs.p1, sid)
                elif idx == 1 and hasattr(gs, 'remap_sid'):
                    gs.remap_sid(gs.p2, sid)
        await _finish(room_code, surrender_by=sid)

    @sio.event
    async def knowledge_state(sid, data):
        """إعادة مزامنة عند reconnect."""
        room_code = (data or {}).get('roomCode')
        room, gs = _room_gs(room_code)
        if not room or not gs.is_player_in_game(sid):
            return
        payload = {
            'stage': gs.stage, 'index': gs.round_index,
            'total': gs.TOTAL_ROUNDS, 'points': gs.points,
            'strikes': gs.strikes,
        }
        if gs.stage == 'turn' and gs.current_q:
            elapsed = time.time() - (gs.turn_started_at or time.time())
            payload.update({
                'q': gs.current_q.get('q', ''),
                'category': gs.current_q.get('cat', ''),
                'turn': gs.turn,
                'seconds_left': max(0, int(gs.TURN_SECONDS - elapsed)),
            })
        await sio.emit('knowledge_state', payload, to=sid)

    _start_round_ref = _start_round
