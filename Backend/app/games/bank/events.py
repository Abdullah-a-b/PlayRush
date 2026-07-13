"""
🏦 لعبة البنك (المتزامنة) — معالجات الأحداث

اللاعبان يلعبان معاً: لكل لاعب أسئلته ومؤقّته وسلّمه.
الوقت يتجمّد أثناء الكتابة/تحكيم AI (عدل)؛ الحماية من استغلاله: انتهاء نافذة الكتابة بلا إجابة = خطأ يمسح الرصيد.
"""
import asyncio
import json
import os
import random
import time

from app.games.core_manager import get_room_state
from app.services.reward_service import record_match_result

_start_first_round = None
_QUESTIONS = None


def _load_questions():
    global _QUESTIONS
    if _QUESTIONS is None:
        here = os.path.abspath(__file__)
        backend_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(here))))
        path = os.path.join(backend_root, "data", "bank_questions.json")
        auto_path = os.path.join(backend_root, "data", "bank_questions_auto.json")
        try:
            with open(path, encoding="utf-8") as f:
                _QUESTIONS = json.load(f)
        except Exception as e:
            print(f"⚠️ [bank] تعذّر تحميل الأسئلة من {path}: {e}")
            _QUESTIONS = []
        # 🔄 دمج المولَّد آلياً من Wikidata (إن وُجد) — معرّفاته wd_ لا تتصادم
        try:
            if os.path.exists(auto_path):
                with open(auto_path, encoding="utf-8") as f:
                    auto_qs = json.load(f)
                existing = {q.get("id") for q in _QUESTIONS}
                _QUESTIONS += [q for q in auto_qs if q.get("id") not in existing]
        except Exception as e:
            print(f"⚠️ [bank] دمج المولّد: {e}")
        print(f"🏦 [bank] حُمّل {len(_QUESTIONS)} سؤال (يدوي + مولّد)")
    return _QUESTIONS


def _seen_ids_for_user(user_id):
    """أسئلة سبق أن شاهدها هذا المستخدم (فلترة شخصية — لا تمس خصمه)."""
    if not user_id:
        return set()
    try:
        from app.core.database import SessionLocal
        from app.models.user import BankSeen
        db = SessionLocal()
        try:
            rows = db.query(BankSeen.question_id).filter(
                BankSeen.user_id == user_id).all()
            return {qid for (qid,) in rows}
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [bank] seen fetch: {e}")
        return set()


def _record_seen_bulk(user_id, question_ids):
    """(يعمل في thread — fire-and-forget عند نهاية المباراة)
    يسجّل كل أسئلة المباراة دفعة واحدة في transaction واحد.
    🐛 إصلاح: الدالة القديمة _record_seen لم تكن تُستدعى أبداً —
    ميزة عدم التكرار كانت تقرأ ولا تكتب!"""
    if not user_id or not question_ids:
        return
    try:
        from app.core.database import SessionLocal
        from app.models.user import BankSeen
        db = SessionLocal()
        try:
            existing = {qid for (qid,) in db.query(BankSeen.question_id).filter(
                BankSeen.user_id == user_id,
                BankSeen.question_id.in_(list(question_ids))).all()}
            for qid in question_ids:
                if qid not in existing:
                    db.add(BankSeen(user_id=user_id, question_id=qid))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [bank] seen bulk: {e}")


def _recycle_seen(user_id):
    """تدوير ذاتي: عند نفاد الأسئلة نحذف أقدم نصف مشاهدات المستخدم."""
    try:
        from app.core.database import SessionLocal
        from app.models.user import BankSeen
        db = SessionLocal()
        try:
            rows = (db.query(BankSeen).filter(BankSeen.user_id == user_id)
                    .order_by(BankSeen.seen_at.asc()).all())
            for r in rows[: max(1, len(rows) // 2)]:
                db.delete(r)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [bank] seen recycle: {e}")


def _pick_question(difficulty, used_ids, user_id=None, _retried=False):
    """يفلتر على: أسئلة المباراة الحالية + مشاهدات هذا اللاعب شخصياً."""
    seen = _seen_ids_for_user(user_id)
    blocked = set(used_ids) | seen
    qs = [q for q in _load_questions()
          if q.get("diff") == difficulty and q.get("id") not in blocked]
    if not qs:  # نفس الصعوبة نفدت → أي صعوبة (النقاط تُحسب من السلّم المعروض)
        qs = [q for q in _load_questions() if q.get("id") not in blocked]
    if not qs and user_id and not _retried:
        # 🔄 نفدت القاعدة لهذا المستخدم → تدوير أقدم مشاهداته وإعادة المحاولة
        _recycle_seen(user_id)
        return _pick_question(difficulty, used_ids, user_id, _retried=True)
    if not qs:  # آخر ملاذ (بلا user_id أو بعد التدوير): تجاهل seen
        qs = [q for q in _load_questions() if q.get("id") not in used_ids]
    if not qs:
        qs = _load_questions()
    return random.choice(qs) if qs else None


async def trigger_bank_start(sio, room_code):
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        return
    gs = room['game_state']
    if gs.stage != 'waiting':
        return
    if _start_first_round is None:
        print("❌ [bank] _start_first_round غير مربوط!")
        return
    await _start_first_round(room_code)


def register_bank_events(sio):
    global _start_first_round

    def _safe_by_name(room, gs):
        """النقاط بأسماء اللاعبين الثابتة — حصينة ضد تقلّب هوية الاتصال."""
        out = {}
        for p in room.get('players', []):
            out[p.get('name', '?')] = gs.safe.get(p.get('sid'), 0)
        return out

    def _room_gs(room_code):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return None, None
        return room, room['game_state']

    async def _start_round(room_code):
        room, gs = _room_gs(room_code)
        if not room or gs.stage == 'finished':
            return
        await sio.emit('bank_round_start', {
            'round': gs.round, 'totalRounds': gs.TOTAL_ROUNDS,
            'turnSeconds': gs.TURN_SECONDS, 'safe': gs.safe,
            'safeByName': _safe_by_name(room, gs),
        }, room=room_code)
        # ننتظر أنيميشن "استعد 3-2-1"
        await asyncio.sleep(3.2)
        room, gs = _room_gs(room_code)
        if not room or gs.stage == 'finished':
            return
        gs.start_round()
        # سؤال أول لكل لاعب + مؤقّت مستقل
        for sid in (gs.p1, gs.p2):
            await _next_question(room_code, sid)
            sio.start_background_task(_player_timer, room_code, sid, gs.round)

    async def _player_timer(room_code, sid, round_no):
        """يراقب انتهاء وقت اللاعب في الجولة → بنك تلقائي + done."""
        while True:
            await asyncio.sleep(0.5)
            room, gs = _room_gs(room_code)
            if not room or room.get('state') != 'playing':
                return
            if gs.stage != 'playing' or gs.round != round_no:
                return
            if gs.pstate[sid]['done']:
                return
            if gs.remaining(sid) <= 0:
                await _end_player_turn(room_code, sid, round_no)
                return

    def _uid_of(room, sid):
        p = next((p for p in room.get('players', []) if p.get('sid') == sid), None)
        return p.get('user_id') if p else None

    async def _next_question(room_code, sid):
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'playing' or gs.pstate[sid]['done']:
            return
        diff = gs.difficulty_now(sid)
        _uid = _uid_of(room, sid)
        # 🚀 المنتقي يقرأ مشاهدات DB — في thread حتى لا يحجب event loop
        q = await asyncio.to_thread(_pick_question, diff, gs.used_question_ids, _uid)
        if not q:
            return
        gs.pstate[sid]['question'] = q
        gs.pstate[sid]['question_diff'] = diff  # الصعوبة المعروضة (النقاط منها!)
        # 📝 نتتبع أسئلة هذا اللاعب لتسجيلها بالجملة عند نهاية المباراة
        gs.pstate[sid].setdefault('asked_ids', []).append(q['id'])
        # 💰 المضاعفة تلتصق بهذا السؤال
        if gs.pstate[sid].pop('double_next', False):
            gs.pstate[sid]['double_active'] = True
        gs.used_question_ids.append(q['id'])
        gs.bump_version()
        # السؤال يذهب للاعبه فقط (كلٌّ بسؤاله)
        await sio.emit('bank_question', {
            'id': q['id'], 'text': q['q'], 'category': q.get('cat', ''),
            'remaining': round(gs.remaining(sid), 1),
        }, to=sid)

    @sio.event
    async def bank_answer_start(sid, data):
        """ضغط 'إجابة' → نافذة كتابة + تجميد المؤقّت (الكتابة لا تأكل وقتك)."""
        room_code = (data or {}).get('roomCode')
        room, gs = _room_gs(room_code)
        if not room or room.get('state') != 'playing':
            return
        if gs.stage != 'playing' or not gs.is_player_in_game(sid):
            return
        ps = gs.pstate[sid]
        if ps['done'] or ps['answering'] or not ps['question']:
            return
        ps['answering'] = True
        gs.freeze(sid)  # ⏸️ الكتابة والتحكيم لا يأكلان وقتك (عدل)
        gs.bump_version()
        await sio.emit('bank_answering', {
            'answerWindow': gs.ANSWER_WINDOW,
            'remaining': round(gs.remaining(sid), 1),
        }, to=sid)
        # نُعلم الخصم (شفافية بلا تفاصيل)
        await sio.emit('bank_opp_activity', {'type': 'answering'}, to=gs.opponent(sid))
        sio.start_background_task(_answer_timeout, room_code, sid,
                                  ps['question']['id'], gs.round)

    async def _answer_timeout(room_code, sid, qid, round_no):
        room, gs = _room_gs(room_code)
        if not room:
            return
        await asyncio.sleep(gs.ANSWER_WINDOW)
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'playing' or gs.round != round_no:
            return
        ps = gs.pstate.get(sid)
        if ps and ps['answering'] and ps['question'] and ps['question']['id'] == qid:
            await _handle_answer(room_code, sid, '', timed_out=True)

    @sio.event
    async def bank_submit_answer(sid, data):
        room_code = (data or {}).get('roomCode')
        answer = ((data or {}).get('answer') or '').strip()
        room, gs = _room_gs(room_code)
        if not room or room.get('state') != 'playing' or gs.stage != 'playing':
            return
        ps = gs.pstate.get(sid)
        if not ps or not ps['answering']:
            return
        await _handle_answer(room_code, sid, answer, timed_out=False)

    def _normalize_digits(s):
        """أرقام عربية → لاتينية + إزالة غير الأرقام."""
        trans = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        return ''.join(ch for ch in str(s).translate(trans) if ch.isdigit())

    async def _handle_answer(room_code, sid, answer, timed_out):
        from app.core.text_processor import check_answer
        room, gs = _room_gs(room_code)
        if not room:
            return
        ps = gs.pstate[sid]
        # 🛡️ حاجز السباق: إجابة مُرسلة عند حافة المهلة + تحكيم AI (≤2ث)
        # كانا قد يدخلان معاً → معالجة مزدوجة (مسح رصيد + تقدّم سؤال ×2).
        # أول داخلٍ يقفل الباب فوراً — قبل أي await، وasyncio أحادي الخيط
        # فالفحص+القفل ذرّيان.
        if not ps.get('answering'):
            return
        ps['answering'] = False
        q = ps['question'] or {}
        correct = q.get('a', '')
        accepted = q.get('accepted', [])
        is_correct = False
        # 🔢 إجابة رقمية (سنة/عدد): مطابقة صارمة فقط — لا fuzzy ولا AI
        # (يمنع قبول 1942 عن 1914 قطعياً)
        correct_digits = _normalize_digits(correct)
        if correct_digits and correct_digits == ''.join(
                ch for ch in str(correct) if not ch.isspace()).translate(
                str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')):
            if not timed_out and answer:
                ans_digits = _normalize_digits(answer)
                acc_digits = {_normalize_digits(a) for a in accepted if _normalize_digits(a)}
                acc_digits.add(correct_digits)
                is_correct = bool(ans_digits) and ans_digits in acc_digits
            # نتجاوز المسار النصي كلياً
            result = {'verdict': 'accept' if is_correct else 'reject'}
        elif not timed_out and answer:
            result = check_answer(answer, correct, accepted, None)
            is_correct = result['verdict'] == 'accept'
            if result.get('verdict') == 'maybe':
                try:
                    # ⚖️ نُعلم اللاعب أن الحكم الذكي يراجع (والوقت مجمّد أصلاً)
                    await sio.emit('bank_judging', {}, to=sid)
                    from app.core.ai_judge import judge_answer
                    judged = await judge_answer(q.get('q', ''), correct, answer, timeout=2.0)
                    is_correct = bool(judged.get('accept', False))
                except Exception:
                    is_correct = False  # فشل AI → رفض آمن
        # ⚖️ النقاط من السلّم الذي رآه اللاعب (لا تصنيف السؤال بالملف —
        # الـfallback عند نفاد صعوبة قد يسحب سؤالاً من فئة أخرى)
        diff = gs.pstate[sid].get('question_diff') or q.get('diff', 'easy')
        pts = gs.points_for(diff)
        gs.unfreeze(sid)  # ▶️ استئناف بعد الكتابة + تحكيم AI (القفل تم أول الدالة)
        # 🔄 فرصة ثانية: خطأ + مفعّلة → نفس السؤال مرة أخرى (+5ث)
        if not is_correct and ps.get('second_chance'):
            ps['second_chance'] = False
            ps['answering'] = True
            gs.freeze(sid)
            gs.bump_version()
            await sio.emit('bank_second_chance', {
                'answerWindow': gs.ANSWER_WINDOW + 5,
                'correctAnswer': None,
            }, to=sid)
            sio.start_background_task(_answer_timeout, room_code, sid,
                                      (ps['question'] or {}).get('id'), gs.round)
            return
        # 💰 مضاعفة السؤال الحالي (فُعّلت قبله)
        if is_correct and ps.get('double_active'):
            pts *= 2
            ps['double_active'] = False
        if is_correct:
            gs.add_temp(sid, pts)
            await sio.emit('bank_answer_result', {
                'correct': True, 'points': pts, 'correctAnswer': correct,
                'temp': gs.temp_of(sid), 'safe': gs.safe,
                'remaining': round(gs.remaining(sid), 1),
            }, to=sid)
            await sio.emit('bank_opp_activity', {'type': 'correct'}, to=gs.opponent(sid))
        else:
            if ps.get('shield'):
                # 🛡️ الدرع يمتص الخطأ — الرصيد محفوظ (يُستهلك)
                ps['shield'] = False
                gs.bump_version()
                await sio.emit('bank_answer_result', {
                    'correct': False, 'lost': 0, 'shielded': True,
                    'correctAnswer': correct,
                    'temp': ps['temp'], 'safe': gs.safe, 'timedOut': timed_out,
                    'remaining': round(gs.remaining(sid), 1),
                }, to=sid)
            else:
                lost = gs.wipe_temp(sid)  # يمسح + يعيد السلّم للسهل
                await sio.emit('bank_answer_result', {
                    'correct': False, 'lost': lost, 'correctAnswer': correct,
                    'temp': 0, 'safe': gs.safe, 'timedOut': timed_out,
                    'remaining': round(gs.remaining(sid), 1),
                }, to=sid)
            await sio.emit('bank_opp_activity', {'type': 'wrong'}, to=gs.opponent(sid))
        # نافذة قرار (صح + رصيد>0): "تبنّك أم تغامر؟" لثانيتين — مثل الأصل
        ps['question'] = None  # لا سؤال معروض (شرط السماح بالبنك)
        gs.bump_version()
        await asyncio.sleep(1.2)
        room, gs = _room_gs(room_code)
        if not room or gs.stage != 'playing':
            return
        ps = gs.pstate[sid]
        if ps['done'] or gs.remaining(sid) <= 0:
            return
        if is_correct and ps['temp'] > 0:
            await sio.emit('bank_decision', {
                'seconds': 5, 'temp': ps['temp'],
                'remaining': round(gs.remaining(sid), 1),
            }, to=sid)
            await asyncio.sleep(5)
            room, gs = _room_gs(room_code)
            if not room or gs.stage != 'playing':
                return
            ps = gs.pstate[sid]
            if ps['done'] or gs.remaining(sid) <= 0:
                return
            if ps['question'] is None:  # لم يبنّك (البنك يجلب سؤاله بنفسه)
                await _next_question(room_code, sid)
        else:
            await _next_question(room_code, sid)

    @sio.event
    async def bank_bank(sid, data):
        """بنك: يحفظ + يعيد السلّم للسهل + سؤال سهل جديد."""
        room_code = (data or {}).get('roomCode')
        room, gs = _room_gs(room_code)
        if not room or room.get('state') != 'playing' or gs.stage != 'playing':
            return
        ps = gs.pstate.get(sid)
        if not ps or ps['done'] or ps['answering']:
            return
        if ps['question'] is not None:
            # 🏦 البنك بين الأسئلة فقط (مثل الأصل: المقدم يسأل قبل السؤال)
            await sio.emit('bank_denied', {'msg': 'البنك متاح بين الأسئلة فقط'}, to=sid)
            return
        amount = gs.bank(sid)
        await sio.emit('bank_banked', {
            'amount': amount, 'safe': gs.safe, 'temp': 0,
            'remaining': round(gs.remaining(sid), 1),
        }, to=sid)
        await sio.emit('bank_opp_activity', {'type': 'banked', 'amount': amount},
                       to=gs.opponent(sid))
        await sio.emit('bank_safe_update', {'safe': gs.safe}, room=room_code)
        # سؤال جديد سهل فوراً
        await asyncio.sleep(0.6)
        room, gs = _room_gs(room_code)
        if room and gs.stage == 'playing' and not gs.pstate[sid]['done'] \
                and gs.remaining(sid) > 0:
            await _next_question(room_code, sid)

    _advancing = set()  # قفل تقدّم الجولة (منع السباق عند انتهاء الاثنين معاً)

    async def _end_player_turn(room_code, sid, round_no):
        room, gs = _room_gs(room_code)
        if not room or gs.round != round_no or gs.pstate[sid]['done']:
            return
        banked = gs.bank(sid)  # بنك تلقائي
        gs.mark_done(sid)
        await sio.emit('bank_player_done', {
            'autoBanked': banked, 'safe': gs.safe,
        }, to=sid)
        await sio.emit('bank_opp_activity', {'type': 'done'}, to=gs.opponent(sid))
        await sio.emit('bank_safe_update', {'safe': gs.safe,
            'safeByName': _safe_by_name(room, gs)}, room=room_code)
        if gs.both_done():
            # 🔒 قفل: مؤقّتا اللاعبَين قد ينتهيان بنفس اللحظة —
            # واحد فقط يقدّم الجولة، والآخر ينسحب بصمت
            if room_code in _advancing:
                return
            _advancing.add(room_code)
            try:
                await asyncio.sleep(1.5)
                room, gs = _room_gs(room_code)
                if not room or gs.stage == 'finished':
                    return
                if gs.round != round_no:
                    return  # جولة أخرى تقدّمت بالفعل
                result = gs.advance_round()
                if result == 'finished':
                    await _finish_match(room_code)
                else:
                    await _start_round(room_code)
            finally:
                _advancing.discard(room_code)

    async def _finish_match(room_code):
        room, gs = _room_gs(room_code)
        if not room:
            return
        if gs.stage == 'finished':
            return  # 🔒 انتهت مسبقاً — لا تسجيل/بث مزدوج
        # 🛡️ شبكة أمان: أي رصيد مؤقت لم يُبنَّك (سباق نادر) يدخل الآمن الآن
        for _sid in (gs.p1, gs.p2):
            if gs.pstate.get(_sid, {}).get('temp', 0) > 0:
                gs.bank(_sid)
        winner_sid = gs.leader()
        gs.winner = winner_sid
        gs.stage = 'finished'
        room['state'] = 'finished'
        # 📝 تسجيل مشاهدات المباراة بالجملة (fire-and-forget، في thread)
        for _sid in (gs.p1, gs.p2):
            _u = _uid_of(room, _sid)
            _qids = list(gs.pstate.get(_sid, {}).get('asked_ids', []))
            if _u and _qids:
                asyncio.create_task(asyncio.to_thread(_record_seen_bulk, _u, _qids))
        if winner_sid:
            wp = next((p for p in room['players'] if p['sid'] == winner_sid), None)
            lp = next((p for p in room['players'] if p['sid'] != winner_sid), None)
            if wp and lp:
                try:
                    # 🚀 في thread — تسجيل النتيجة فيه قفل صف + عدة استعلامات
                    await asyncio.to_thread(
                        record_match_result, wp, lp, 'bank',
                        extra={'friendly': room.get('type') == 'friendly'})
                except Exception as e:
                    print(f"⚠️ [bank] خطأ تسجيل: {e}")
        _wname = next((p.get('name') for p in room['players']
                       if p.get('sid') == winner_sid), None)
        await sio.emit('bank_match_over', {
            'winner': winner_sid, 'winnerName': _wname, 'safe': gs.safe,
            'safeByName': _safe_by_name(room, gs),
        }, room=room_code)

    @sio.event
    async def bank_surrender(sid, data):
        room_code = (data or {}).get('roomCode')
        room, gs = _room_gs(room_code)
        if not room or not gs.is_player_in_game(sid):
            return
        winner_sid = gs.opponent(sid)
        gs.stage = 'finished'
        room['state'] = 'finished'
        # 📝 تسجيل مشاهدات المباراة بالجملة (حتى عند الانسحاب)
        for _sid in (gs.p1, gs.p2):
            _u = _uid_of(room, _sid)
            _qids = list(gs.pstate.get(_sid, {}).get('asked_ids', []))
            if _u and _qids:
                asyncio.create_task(asyncio.to_thread(_record_seen_bulk, _u, _qids))
        wp = next((p for p in room['players'] if p['sid'] == winner_sid), None)
        lp = next((p for p in room['players'] if p['sid'] == sid), None)
        if wp and lp:
            try:
                await asyncio.to_thread(
                    record_match_result, wp, lp, 'bank',
                    extra={'reason': 'surrender',
                           'friendly': room.get('type') == 'friendly'})
            except Exception as e:
                print(f"⚠️ [bank] خطأ انسحاب: {e}")
        _wname = next((p.get('name') for p in room['players']
                       if p.get('sid') == winner_sid), None)
        await sio.emit('bank_match_over', {
            'winner': winner_sid, 'winnerName': _wname, 'safe': gs.safe,
            'safeByName': _safe_by_name(room, gs), 'surrendered': True,
        }, room=room_code)


    # ==========================================
    # 🎯 المساعدات (Play to Win)
    # ==========================================
    @sio.event
    async def bank_use_help(sid, data):
        """استخدام مساعدة. data: { roomCode, helpId }"""
        from app.games.bank.helps import get_help
        from app.games.core_manager import _allow_same_ip
        room_code = (data or {}).get('roomCode')
        help_id = (data or {}).get('helpId')
        room, gs = _room_gs(room_code)
        if not room or room.get('state') != 'playing' or gs.stage != 'playing':
            return
        if not gs.is_player_in_game(sid):
            return
        ps = gs.pstate[sid]
        if ps['done']:
            return
        h = get_help(help_id)
        if not h:
            await sio.emit('bank_help_result', {'ok': False, 'msg': 'مساعدة غير معروفة'}, to=sid)
            return
        used = gs.helps_used.setdefault(sid, set()) if hasattr(gs, 'helps_used') else None
        if used is None:
            gs.helps_used = {}
            used = gs.helps_used.setdefault(sid, set())
        if help_id in used:
            await sio.emit('bank_help_result', {'ok': False, 'msg': 'استخدمتها في هذه المباراة'}, to=sid)
            return
        # قيود التوقيت
        timing = h.get('timing')
        if timing == 'question' and (not ps['question'] or ps['answering']):
            await sio.emit('bank_help_result', {'ok': False, 'msg': 'تُستخدم وسؤالك معروض'}, to=sid)
            return
        # الاستهلاك (وضع التطوير = ∞)
        dev_mode = _allow_same_ip()
        user_id = None
        _pl = next((p for p in room['players'] if p.get('sid') == sid), None)
        if _pl:
            user_id = _pl.get('user_id')
        if not dev_mode and user_id:
            from app.services.help_inventory import consume_help
            if not consume_help(user_id, help_id):
                await sio.emit('bank_help_result', {'ok': False, 'msg': 'لا تملك هذه المساعدة'}, to=sid)
                return
        used.add(help_id)

        # ===== التأثيرات =====
        if help_id == 'b_skip':
            # سؤال بديل بنفس صعوبة السلّم (بلا عقوبة)
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': '⏭️ سؤال بديل!'}, to=sid)
            await _next_question(room_code, sid)
        elif help_id == 'b_first_letter':
            ans = ((ps['question'] or {}).get('a') or '').strip()
            first = ans[0] if ans else '؟'
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': f'🔤 أول حرف: "{first}"'}, to=sid)
        elif help_id == 'b_time_plus':
            # +10ث: نرجع started_at للخلف
            if ps['started_at'] is not None:
                ps['started_at'] += 10
            gs.bump_version()
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': '⏱️ +10 ثوانٍ!', 'remaining': round(gs.remaining(sid), 1)}, to=sid)
        elif help_id == 'b_shield':
            ps['shield'] = True
            gs.bump_version()
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': '🛡️ درعك مفعّل — خطؤك القادم لا يمسح رصيدك'}, to=sid)
        elif help_id == 'b_double_next':
            ps['double_next'] = True
            gs.bump_version()
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': '💰 سؤالك القادم ×2 نقاطاً — بالتوفيق!'}, to=sid)
        elif help_id == 'b_second_chance':
            ps['second_chance'] = True
            gs.bump_version()
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': '🔄 فرصة ثانية مفعّلة عند خطئك القادم'}, to=sid)
        elif help_id == 'b_hard_boost':
            # قفزة للصعب: نرجع ladder_base بحيث elapsed-base >= 2*STEP
            ps['ladder_base'] = gs.elapsed(sid) - (gs.LADDER_STEP * 2)
            gs.bump_version()
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': '🚀 قفزت للصعب — 3 نقاط لكل سؤال!'}, to=sid)
        elif help_id == 'b_flash_bank':
            amount = gs.bank(sid)
            await sio.emit('bank_help_result', {'ok': True, 'helpId': help_id,
                'info': f'⚡ بنك خاطف! حُفظ {amount}'}, to=sid)
            await sio.emit('bank_banked', {
                'amount': amount, 'safe': gs.safe, 'temp': 0, 'flash': True,
                'remaining': round(gs.remaining(sid), 1),
            }, to=sid)
            await sio.emit('bank_safe_update', {'safe': gs.safe,
                'safeByName': _safe_by_name(room, gs)}, room=room_code)
        # إشعار الخصم (شفافية بلا كشف المحتوى)
        opp = gs.opponent(sid)
        await sio.emit('bank_opponent_used_help', {'helpId': help_id,
            'name': h.get('name'), 'icon': h.get('icon')}, to=opp)

    @sio.event
    async def bank_send_emoji(sid, data):
        """إرسال إيموجي متحرك. data: { roomCode, emojiId }"""
        from app.core.anticheat import check_action_rate
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
        rate_issue = check_action_rate(sid, 'bank_send_emoji', max_per_second=1)
        if rate_issue:
            return
        opp = gs.p2 if sid == gs.p1 else gs.p1
        await sio.emit('bank_emoji', {'emojiId': emoji_id, 'isMine': True}, to=sid)
        await sio.emit('bank_emoji', {'emojiId': emoji_id, 'isMine': False}, to=opp)

    @sio.event
    async def bank_get_my_emojis(sid, data):
        """يُرجع إيموجيات اللاعب المملوكة (الأساسية + المشتراة)."""
        room_code = (data or {}).get('roomCode')
        room = get_room_state(room_code)
        base = ['emoji_laugh', 'emoji_cry', 'emoji_angry', 'emoji_think']
        owned = list(base)
        if room and room.get('game_state'):
            user_id = (room.get('user_ids') or {}).get(sid)
            if not user_id:
                _pl = next((p for p in room['players'] if p.get('sid') == sid), None)
                user_id = _pl.get('user_id') if _pl else None
            if user_id:
                try:
                    from app.services.cosmetics import get_owned_cosmetics
                    for c in get_owned_cosmetics(user_id):
                        if c.startswith('emoji_') and c not in owned:
                            owned.append(c)
                except Exception:
                    pass
        await sio.emit('bank_my_emojis', {'owned': owned}, to=sid)


    # ==========================================
    # 🎯 المساعدات (Play to Win — لا تكشف الإجابة)
    # ==========================================
    @sio.event
    async def career_use_help(sid, data):
        """استخدام مساعدة. data: { roomCode, helpId, token }"""
        from app.games.career.helps import get_help
        from app.games.core_manager import _allow_same_ip
        room_code = (data or {}).get('roomCode')
        help_id = (data or {}).get('helpId')
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return
        gs = room['game_state']
        if not gs.is_player_in_game(sid):
            return
        h = get_help(help_id)
        if not h:
            await sio.emit('career_help_result', {'ok': False, 'msg': 'مساعدة غير معروفة'}, to=sid)
            return
        # مرة واحدة لكل مساعدة بالمباراة
        used = gs.helps_used.setdefault(sid, set())
        if help_id in used:
            await sio.emit('career_help_result', {'ok': False, 'msg': 'استخدمتها في هذه المباراة'}, to=sid)
            return
        # قيود التوقيت
        timing = h.get('timing')
        if timing == 'buzzed' and not (gs.stage == 'buzzed' and gs.buzzed_player == sid):
            await sio.emit('career_help_result', {'ok': False, 'msg': 'تُستخدم أثناء كتابتك بعد الجرس'}, to=sid)
            return
        if timing == 'revealing' and gs.stage not in ('revealing', 'buzzed'):
            await sio.emit('career_help_result', {'ok': False, 'msg': 'لا يمكن استخدامها الآن'}, to=sid)
            return
        # قيد كسر التعادل (الدرع والقفل)
        if help_id in ('c_strike_shield', 'c_double_lock') and gs.tiebreaker:
            await sio.emit('career_help_result', {'ok': False, 'msg': 'لا تعمل في جولة كسر التعادل'}, to=sid)
            return
        # الاستهلاك من المخزون (وضع التطوير = لا نهائية مثل حروف)
        dev_mode = _allow_same_ip()
        user_id = None
        _pl = next((p for p in room['players'] if p.get('sid') == sid), None)
        if _pl:
            user_id = _pl.get('user_id')
        if not dev_mode and user_id:
            from app.services.help_inventory import consume_help
            if not consume_help(user_id, help_id):
                await sio.emit('career_help_result', {'ok': False, 'msg': 'لا تملك هذه المساعدة'}, to=sid)
                return
        used.add(help_id)
        cp = gs.current_player or {}

        # التأثيرات
        if help_id == 'c_extend_write':
            gs.answer_extended = True  # مؤقّت المهلة يلتقطها
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': '+5 ثوانٍ لكتابتك ⏱️', 'extendSeconds': 5}, to=sid)
        elif help_id == 'c_nationality':
            nat = cp.get('nationality') or 'غير معروفة'
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': f'🌍 الجنسية: {nat}'}, to=sid)
        elif help_id == 'c_club_count':
            total = len(cp.get('clubs', []))
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': f'📊 إجمالي الأندية: {total}'}, to=sid)
        elif help_id == 'c_first_letter':
            name = (cp.get('name') or '').strip()
            first = name[0] if name else '؟'
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': f'🔤 أول حرف: "{first}"'}, to=sid)
        elif help_id == 'c_strike_shield':
            shields = getattr(gs, 'shields', None)
            if shields is None:
                gs.shields = {}
                shields = gs.shields
            shields[sid] = True
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': '🛡️ درعك مفعّل — أول خطأ لا يُحسب'}, to=sid)
        elif help_id == 'c_era':
            era = cp.get('era') or 'غير متوفرة لهذا اللاعب'
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': f'🎂 فترة المسيرة: {era}'}, to=sid)
        elif help_id == 'c_position':
            pos = cp.get('position') or 'غير متوفر لهذا اللاعب'
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': f'🎯 المركز: {pos}'}, to=sid)
        elif help_id == 'c_double_lock':
            locks = getattr(gs, 'double_locks', None)
            if locks is None:
                gs.double_locks = {}
                locks = gs.double_locks
            locks[sid] = True
            await sio.emit('career_help_result', {'ok': True, 'helpId': help_id,
                'info': '🔒 قفل النقطتين مفعّل لهذه الشخصية'}, to=sid)
        # إشعار الخصم باستخدام مساعدة (شفافية بلا كشف المحتوى)
        opp = gs.opponent(sid)
        await sio.emit('career_opponent_used_help', {'helpId': help_id,
            'name': h.get('name'), 'icon': h.get('icon')}, to=opp)



    async def _start_first_round_impl(room_code):
        await _start_round(room_code)

    _start_first_round = _start_first_round_impl
