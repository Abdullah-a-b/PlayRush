"""
 مسيرة لاعب — معالجات الأحداث (Socket.IO)
"""
import asyncio
import json
import random
import time

from app.infrastructure.database import SessionLocal
from app.domains.games.models import CareerPlayer
from app.domains.games.core_manager import get_room_state
from app.domains.wallet.reward_service import record_match_result
from app.core.text_processor import check_answer


# مرجع للدالة التي تبدأ اللعبة (تُضبط عند التسجيل، لتُستدعى من room_events)
_start_first_player = None


async def trigger_career_start(sio, room_code):
    """يبدأ مباراة career (يُستدعى من room_events عند انضمام الطرفين)."""
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        print(f" [career] trigger: لا غرفة/حالة | room={room_code}")
        return
    gs = room['game_state']
    if gs.stage != 'waiting':
        print(f" [career] trigger: اللعبة بدأت already (stage={gs.stage})")
        return
    if _start_first_player is None:
        print(f" [career] trigger: _start_first_player غير مربوط!")
        return
    # ⏳ ننتظر أنيميشن "استعد 3-2-1" في الواجهة قبل أول لاعب
    import asyncio as _aio
    await _aio.sleep(3.2)
    room = get_room_state(room_code)
    if not room or not room.get('game_state') or room['game_state'].stage != 'waiting':
        return  # تغيّرت الحالة أثناء الاستعداد
    await _start_first_player(room_code)


def register_career_events(sio):
    # معالجات الصداقة/الحظر داخل اللعب (مشتركة)
    from app.domains.games.sockets.social_handlers import register_social_handlers
    register_social_handlers(sio, get_room_state)
    global _start_first_player

    def _load_random_player(used_ids, user_ids=None):
        """اختيار شخصية عادل: غير مُشاهَدة لأيّ من طرفَي المباراة.
        الطبقات: (1) غير مُشاهَد للطرفين  (2) تدوير ذاتي (حذف أقدم
        نصف المشاهدات) وإعادة  (3) عشوائي (نادر مع قاعدة كبيرة)."""
        from app.domains.games.models import CareerSeen
        db = SessionLocal()
        try:
            user_ids = [u for u in (user_ids or []) if u]

            def _pick_id(exclude_seen):
                # نجلب المعرّفات فقط (لا كامل الصفوف) — أسرع بكثير
                q = db.query(CareerPlayer.id).filter(CareerPlayer.active == True)
                if used_ids:
                    q = q.filter(~CareerPlayer.id.in_(used_ids))
                if exclude_seen and user_ids:
                    seen_ids = [pid for (pid,) in db.query(CareerSeen.player_id)
                                .filter(CareerSeen.user_id.in_(user_ids)).all()]
                    if seen_ids:
                        q = q.filter(~CareerPlayer.id.in_(seen_ids))
                ids = [i for (i,) in q.all()]
                return random.choice(ids) if ids else None

            pid = _pick_id(exclude_seen=True)

            if pid is None and user_ids:
                # تدوير ذاتي: نحذف أقدم نصف مشاهدات كل طرف ونعيد
                for uid in user_ids:
                    rows = (db.query(CareerSeen)
                            .filter(CareerSeen.user_id == uid)
                            .order_by(CareerSeen.seen_at.asc()).all())
                    for r in rows[: max(1, len(rows) // 2)]:
                        db.delete(r)
                db.commit()
                pid = _pick_id(exclude_seen=True)

            if pid is None:
                pid = _pick_id(exclude_seen=False)  # آخر ملاذ
            if pid is None:
                return None

            cp = db.query(CareerPlayer).filter(CareerPlayer.id == pid).first()
            if not cp:
                return None

            # نسجّل المشاهدة للطرفين فوراً
            for uid in user_ids:
                exists = db.query(CareerSeen).filter(
                    CareerSeen.user_id == uid,
                    CareerSeen.player_id == cp.id).first()
                if not exists:
                    db.add(CareerSeen(user_id=uid, player_id=cp.id))
            db.commit()

            return {
                'id': cp.id, 'name': cp.name, 'status': cp.status,
                'clubs': json.loads(cp.clubs) if cp.clubs else [],
                'accepted_answers': json.loads(cp.accepted_answers) if cp.accepted_answers else [],
                'nationality': cp.nationality,
                'era': getattr(cp, 'era', None),
                'position': getattr(cp, 'position', None),
            }
        finally:
            db.close()

    async def _emit_reveal_state(room_code, gs, extra=None):
        payload = {
            'clubs': gs.revealed_clubs(),
            'status': (gs.current_player or {}).get('status', 'retired'),
            'careerComplete': gs.career_complete,
            'revealedCount': gs.revealed_count,
            'totalClubs': len((gs.current_player or {}).get('clubs', [])),
            'scores': gs.scores, 'strikes': gs.strikes,
            'pointsIfAnswer': gs.score_for_current(),
            'playerIndex': gs.player_index, 'totalPlayers': gs.TOTAL_PLAYERS,
            'tiebreaker': gs.tiebreaker,
        }
        if extra:
            payload.update(extra)
        await sio.emit('career_reveal_state', payload, room=room_code)

    async def _reveal_loop(room_code, version, resume_seconds=None):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        first_wait = resume_seconds if resume_seconds is not None else gs.REVEAL_INTERVAL
        while True:
            if gs.state_version != version:
                return
            gs.reveal_started_at = time.time()
            gs.reveal_wait = first_wait
            await asyncio.sleep(first_wait)
            first_wait = gs.REVEAL_INTERVAL
            room = get_room_state(room_code)
            if not room or room.get('state') != 'playing' or not room.get('game_state'):
                return
            gs = room['game_state']
            if gs.state_version != version or gs.stage != 'revealing':
                return
            revealed = gs.reveal_next_club()
            version = gs.state_version
            if not revealed or gs.career_complete:
                # آخر نادٍ: نافذة أخيرة 10 ثوانٍ (فرصة إجابة بنقطة) ثم استبدال
                final_wait = getattr(gs, 'FINAL_WINDOW', 10)
                await _emit_reveal_state(room_code, gs, extra={
                    'careerJustCompleted': True, 'windowSeconds': final_wait})
                gs.reveal_started_at = time.time()
                gs.reveal_wait = final_wait
                await asyncio.sleep(final_wait)
                room = get_room_state(room_code)
                if not room or not room.get('game_state'):
                    return
                gs = room['game_state']
                if gs.stage == 'revealing' and gs.state_version == version:
                    await _replace_player(room_code)
                return
            # كشف عادي: الشريط يطابق الفاصل الفعلي (5 ثوانٍ)
            await _emit_reveal_state(room_code, gs, extra={
                'windowSeconds': gs.REVEAL_INTERVAL})

    async def _start_player(room_code, advance=True, replace=False):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        # لا نبدأ شخصية لو انتهت المباراة (انسحاب/فوز أثناء توقف انتقالي)
        if room.get('state') == 'finished' or gs.stage == 'finished':
            return
        if advance and not replace and gs.all_players_done():
            await _resolve_end(room_code)
            return
        # معرّفات المستخدمين (لفلترة الشخصيات المُشاهَدة للطرفين)
        _uids = [p.get('user_id') for p in room.get('players', []) if p.get('user_id')]
        player = _load_random_player(gs.used_player_ids, user_ids=_uids)
        if not player:
            await _resolve_end(room_code, forced=True)
            return
        gs.start_new_player(player, advance_index=advance)
        await sio.emit('career_new_player', {
            'status': player['status'], 'totalClubs': len(player['clubs']),
            'scores': gs.scores, 'playerIndex': gs.player_index,
            'totalPlayers': gs.TOTAL_PLAYERS, 'tiebreaker': gs.tiebreaker, 'replaced': replace,
        }, room=room_code)
        await _emit_reveal_state(room_code, gs, extra={
            'windowSeconds': gs.REVEAL_INTERVAL})
        sio.start_background_task(_reveal_loop, room_code, gs.state_version)

    _replacing = set()  # غرف يجري فيها استبدال الآن (منع الاستبدال المزدوج)

    async def _replace_player(room_code):
        if room_code in _replacing:
            return  # استبدال آخر جارٍ — لا نكرر
        _replacing.add(room_code)
        try:
            await sio.emit('career_player_skipped', {}, room=room_code)
            room = get_room_state(room_code)
            if room and room.get('game_state'):
                gs = room['game_state']
                correct = (gs.current_player or {}).get('name', '')
                await sio.emit('career_reveal_answer', {'playerName': correct}, room=room_code)
                await asyncio.sleep(1.5)
            await _start_player(room_code, advance=False, replace=True)
        finally:
            _replacing.discard(room_code)

    async def _resolve_end(room_code, forced=False):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if gs.is_tie() and not forced:
            gs.tiebreaker = True
            await sio.emit('career_tiebreaker', {'scores': gs.scores}, room=room_code)
            await asyncio.sleep(1.5)
            await _start_player(room_code, advance=True)
            return
        await _finish_match(room_code, gs.leader())

    async def _finish_match(room_code, winner_sid):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        gs.winner = winner_sid
        gs.stage = 'finished'
        room['state'] = 'finished'
        if winner_sid:
            wp = next((p for p in room['players'] if p['sid'] == winner_sid), None)
            lp = next((p for p in room['players'] if p['sid'] != winner_sid), None)
            if wp and lp:
                try:
                    # في thread — لا يحجب event loop (قفل صف + عدة استعلامات)
                    await asyncio.to_thread(
                        record_match_result, wp, lp, 'career',
                        extra={'friendly': room.get('type') == 'friendly',
                               'winner_score': gs.scores.get(winner_sid, 0)})
                except Exception as e:
                    print(f" [career] خطأ تسجيل: {e}")
        await sio.emit('career_match_over', {'winner': winner_sid, 'scores': gs.scores}, room=room_code)

    @sio.event
    async def career_start(sid, data):
        """
         هذا الحدث للغرف الخاصة فقط (private).
        الغرف العامة (public/matchmaking) تبدأ تلقائياً من trigger_career_start في room_events.
        نمنع التشغيل المزدوج بالتحقق من stage + room type.
        """
        room_code = data.get('roomCode')
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        # منع التشغيل المزدوج: لو اللعبة بدأت بالفعل (من trigger أو حدث آخر) نتجاهل
        if gs.stage != 'waiting':
            print(f" [career] career_start مكرر (stage={gs.stage}) — تجاهل | room={room_code}")
            return
        # الغرف العامة تبدأ من room_events لا من هنا
        if room.get('type') == 'public':
            print(f" [career] career_start من غرفة عامة — تجاهل (يبدأ تلقائياً) | room={room_code}")
            return
        await _start_player(room_code, advance=True)

    @sio.event
    async def career_buzz(sid, data):
        room_code = data.get('roomCode')
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return
        gs = room['game_state']
        if not gs.can_buzz(sid):
            return
        started = getattr(gs, 'reveal_started_at', None)
        wait = getattr(gs, 'reveal_wait', gs.REVEAL_INTERVAL)
        if started is not None:
            elapsed = time.time() - started
            gs.reveal_remaining = max(0.5, wait - elapsed)
        else:
            gs.reveal_remaining = gs.REVEAL_INTERVAL
        gs.register_buzz(sid)
        await sio.emit('career_buzzed', {'sid': sid, 'answerWindow': gs.ANSWER_WINDOW}, room=room_code)
        sio.start_background_task(_answer_timeout, room_code, gs.state_version, sid)

    async def _answer_timeout(room_code, version, buzzer_sid):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        gs.answer_extended = False
        await asyncio.sleep(gs.ANSWER_WINDOW)
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        # ⏱ تمديد الكتابة: +5 ثوانٍ لو فُعّلت أثناء النافذة
        if getattr(gs, 'answer_extended', False) and gs.stage == 'buzzed' \
                and gs.buzzed_player == buzzer_sid and gs.state_version == version:
            await asyncio.sleep(5)
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if gs.stage == 'buzzed' and gs.buzzed_player == buzzer_sid and gs.state_version == version:
            await _handle_strike(room_code, buzzer_sid, timed_out=True)

    @sio.event
    async def career_submit_answer(sid, data):
        room_code = data.get('roomCode')
        answer = (data.get('answer') or '').strip()
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return
        gs = room['game_state']
        if gs.stage != 'buzzed' or gs.buzzed_player != sid:
            return
        # الإرسال يلتزم: نبطل مؤقّت نافذة الكتابة فوراً (بالإصدار) —
        # كان قد ينفجر أثناء تحكيم AI (≤2ث) ويضرب سترايك رغم إجابة قيد الحسم.
        gs.bump_version()
        correct_name = (gs.current_player or {}).get('name', '')
        accepted = (gs.current_player or {}).get('accepted_answers', [])
        result = check_answer(answer, correct_name, accepted, None)
        is_correct = result['verdict'] == 'accept'
        if result.get('verdict') == 'maybe':
            # الحالة الحدّية: نسأل AI. لو فشل أو شكّ  نرفض (لا نقبل إجابة خاطئة!)
            try:
                # الطرفان يريان أن الحكم الذكي يراجع (شفافية + تفسير التوقف)
                await sio.emit('career_judging', {'sid': sid}, room=room_code)
                from app.infrastructure.ai_judge import judge_answer
                clubs = [c['name'] for c in (gs.current_player or {}).get('clubs', [])]
                judged = await judge_answer(f"لاعب كرة مسيرته: {clubs}", correct_name, answer, timeout=2.0)
                is_correct = bool(judged.get('accept', False))  # الافتراضي: رفض
            except Exception:
                is_correct = False  # فشل AI  رفض آمن (لا نمنح نقطة بالخطأ)
        if is_correct:
            points = gs.score_for_current()
            # قفل النقطتين: إجابة صحيحة بعد الاكتمال = نقطتان (يُستهلك)
            locks = getattr(gs, 'double_locks', {})
            if points == 1 and locks.get(sid):
                points = 2
                locks[sid] = False
                await sio.emit('career_double_lock_used', {'sid': sid}, room=room_code)
            gs.award(sid, points)
            await sio.emit('career_answer_result', {
                'sid': sid, 'correct': True, 'points': points,
                'playerName': correct_name, 'scores': gs.scores,
            }, room=room_code)
            await asyncio.sleep(1.8)
            if gs.all_players_done():
                await _resolve_end(room_code)
            else:
                await _start_player(room_code, advance=True)
        else:
            await _handle_strike(room_code, sid, timed_out=False)

    async def _handle_strike(room_code, sid, timed_out):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        # درع السترايك: أول خطأ لا يُحسب (يُستهلك)
        shields = getattr(gs, 'shields', {})
        if shields.get(sid):
            shields[sid] = False
            await sio.emit('career_shield_used', {'sid': sid}, room=room_code)
            resume = gs.reveal_remaining if gs.reveal_remaining is not None else gs.REVEAL_INTERVAL
            gs.stage = 'revealing'
            gs.buzzed_player = None
            gs.bump_version()
            await _emit_reveal_state(room_code, gs, extra={'resumed': True, 'resumeSeconds': resume})
            if gs.career_complete:
                gs.reveal_started_at = time.time()
                gs.reveal_wait = resume
                _sv = gs.state_version
                await asyncio.sleep(resume)
                room = get_room_state(room_code)
                if room and room.get('game_state'):
                    gs = room['game_state']
                    if gs.stage == 'revealing' and gs.state_version == _sv:
                        await _replace_player(room_code)
            else:
                sio.start_background_task(_reveal_loop, room_code, gs.state_version, resume)
            return
        strikes = gs.add_strike(sid)
        correct_name = (gs.current_player or {}).get('name', '')
        await sio.emit('career_strike', {
            'sid': sid, 'strikes': gs.strikes, 'timedOut': timed_out,
            'count': strikes, 'maxStrikes': gs.MAX_STRIKES,
        }, room=room_code)
        if gs.both_struck_out():
            await _replace_player(room_code)
            return
        resume = gs.reveal_remaining if gs.reveal_remaining is not None else gs.REVEAL_INTERVAL
        gs.stage = 'revealing'
        gs.buzzed_player = None
        gs.bump_version()
        await _emit_reveal_state(room_code, gs, extra={'resumed': True, 'resumeSeconds': resume})
        if gs.career_complete:
            # نحدّث bookkeeping المؤقّت (حتى يحسب أي جرس لاحق "المتبقي" صح)
            gs.reveal_started_at = time.time()
            gs.reveal_wait = resume
            _v = gs.state_version  # لمنع "الاستبدال الشبح" لو تغيّرت الحالة أثناء النوم
            await asyncio.sleep(resume)
            room = get_room_state(room_code)
            if room and room.get('game_state'):
                gs = room['game_state']
                if gs.stage == 'revealing' and gs.state_version == _v:
                    await _replace_player(room_code)
        else:
            sio.start_background_task(_reveal_loop, room_code, gs.state_version, resume)

    @sio.event
    async def career_surrender(sid, data):
        room_code = data.get('roomCode')
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if not gs.is_player_in_game(sid):
            return
        winner_sid = gs.opponent(sid)
        gs.stage = 'finished'
        room['state'] = 'finished'
        wp = next((p for p in room['players'] if p['sid'] == winner_sid), None)
        lp = next((p for p in room['players'] if p['sid'] == sid), None)
        if wp and lp:
            try:
                await asyncio.to_thread(
                    record_match_result, wp, lp, 'career',
                    extra={'reason': 'surrender', 'friendly': room.get('type') == 'friendly'})
            except Exception as e:
                print(f" [career] خطأ انسحاب: {e}")
        await sio.emit('career_match_over', {
            'winner': winner_sid, 'scores': gs.scores, 'surrendered': True,
        }, room=room_code)

    # ==========================================
    # الإيموجيات المتحركة (نفس نظام حروف)
    # ==========================================
    @sio.event
    async def career_send_emoji(sid, data):
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
        rate_issue = check_action_rate(sid, 'career_send_emoji', max_per_second=1)
        if rate_issue:
            return
        opp = gs.p2 if sid == gs.p1 else gs.p1
        await sio.emit('career_emoji', {'emojiId': emoji_id, 'isMine': True}, to=sid)
        await sio.emit('career_emoji', {'emojiId': emoji_id, 'isMine': False}, to=opp)

    @sio.event
    async def career_get_my_emojis(sid, data):
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
                    from app.domains.wallet.cosmetics import get_owned_cosmetics
                    for c in get_owned_cosmetics(user_id):
                        if c.startswith('emoji_') and c not in owned:
                            owned.append(c)
                except Exception:
                    pass
        await sio.emit('career_my_emojis', {'owned': owned}, to=sid)


    # ==========================================
    # المساعدات (Play to Win — لا تكشف الإجابة)
    # ==========================================
    @sio.event
    async def career_use_help(sid, data):
        """استخدام مساعدة. data: { roomCode, helpId, token }"""
        from app.domains.games.career.helps import get_help
        from app.domains.games.core_manager import _allow_same_ip
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
        # 🤖 الوضع الفردي: لا خصم من مخزون اللاعب (تدريب لا مقامرة).
        #    تتجدّد كل مباراة فردية، ويبقى قيد "مرة لكل مباراة" ساريًا.
        _is_solo = bool(getattr(gs, "is_solo", False))
        if not dev_mode and not _is_solo and user_id:
            from app.domains.wallet.help_inventory import consume_help
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

    # نربط دالة البدء بالمرجع العام (لتُستدعى من room_events عند الانضمام)
    _start_first_player = _start_player


async def send_career_reconnect_state(sio, room_code: str, sid: str):
    """
    يُرسل حالة مباراة career الحالية للاعب العائد بعد انقطاع.
    يُستدعى من room_events عند reconnect في غرفة career.
    """
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        return
    gs = room['game_state']
    if gs.stage == 'waiting' or gs.stage == 'finished':
        return

    clubs = (gs.current_player or {}).get('clubs', [])
    payload = {
        'reconnect': True,
        'stage': gs.stage,
        'clubs': clubs[: gs.revealed_count],
        'status': (gs.current_player or {}).get('status', 'retired'),
        'careerComplete': gs.career_complete,
        'revealedCount': gs.revealed_count,
        'totalClubs': len(clubs),
        'scores': gs.scores,
        'strikes': gs.strikes,
        'pointsIfAnswer': gs.score_for_current(),
        'playerIndex': gs.player_index,
        'totalPlayers': gs.TOTAL_PLAYERS,
        'tiebreaker': gs.tiebreaker,
        'buzzedPlayer': gs.buzzed_player,
    }
    await sio.emit('career_reveal_state', payload, to=sid)