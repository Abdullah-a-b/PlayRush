"""
أحداث «من أنا» — Who Am I

نفس عمود مسيرة الفقري: حلقة كشف بحارس إصدار، جرس يوقف الكشف ويفتح
نافذة كتابة 10 ثوانٍ، تحكيم نصّي بطبقات + حكم ذكي للحالات الحدّية،
سترايكان يقصيان من الشخصية، وكشف الإجابة والانتقال عند عجز الطرفين.
"""
import json
import time
import random
import asyncio

from app.domains.games.core_manager import get_room_state
from app.domains.games.whoami.engine import WhoamiGameState
from app.domains.wallet.reward_service import record_match_result
from app.core.text_processor import check_answer
from app.core.paths import DATA_DIR

_start_first_character = None
_CHARS_FILE = str(DATA_DIR / "whoami_characters.json")
_chars_cache = None


def _load_pool():
    """تحميل قاعدة الشخصيات (مرة واحدة لكل عملية)."""
    global _chars_cache
    if _chars_cache is None:
        try:
            with open(_CHARS_FILE, encoding="utf-8") as f:
                _chars_cache = (json.load(f) or {}).get("characters", [])
        except Exception as e:
            print(f" [whoami] فشل تحميل الشخصيات: {e}")
            _chars_cache = []
    return _chars_cache


async def trigger_whoami_start(sio, room_code):
    """يبدأ المباراة (يُستدعى من room_events عند انضمام الطرفين)."""
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        return
    gs = room['game_state']
    if gs.stage != 'waiting':
        return
    if _start_first_character is None:
        print(" [whoami] trigger: _start_first_character غير مربوط!")
        return
    # ننتظر أنيميشن "استعد" في الواجهة قبل أول شخصية
    await asyncio.sleep(3.2)
    room = get_room_state(room_code)
    if not room or not room.get('game_state') or room['game_state'].stage != 'waiting':
        return
    await _start_first_character(room_code)


def register_whoami_events(sio):
    global _start_first_character

    def _pick_character(used_ids):
        pool = [c for c in _load_pool() if c.get('id') not in set(used_ids)]
        if not pool:
            return None
        return dict(random.choice(pool))

    def _name_of(room, sid):
        pl = next((p for p in room.get('players', []) if p.get('sid') == sid), None)
        return (pl or {}).get('name', 'لاعب')

    async def _emit_reveal_state(room_code, gs, extra=None):
        payload = {
            'hints': gs.revealed_hints(),
            'category': '',  # 🙈 حصرية لمساعدة كشف الفئة
            'hintsDone': gs.hints_done,
            'revealedCount': gs.revealed_count,
            'totalHints': len((gs.current or {}).get('hints', [])),
            'scores': gs.scores, 'strikes': gs.strikes,
            'pointsIfAnswer': gs.score_for_current(),
            'charIndex': gs.char_index, 'totalCharacters': gs.TOTAL_CHARACTERS,
            'tiebreaker': gs.tiebreaker,
            'helps_used': {k: list(v) for k, v in gs.helps_used.items()},
            'shield_active': gs.shield_active,
            'locked_points': gs.locked_points,
        }
        if extra:
            payload.update(extra)
        await sio.emit('whoami_reveal_state', payload, room=room_code)

    async def _reveal_loop(room_code, version, resume_seconds=None):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        first_wait = resume_seconds if resume_seconds is not None else gs.HINT_INTERVAL
        while True:
            if gs.state_version != version:
                return
            gs.reveal_started_at = time.time()
            gs.reveal_wait = first_wait
            await asyncio.sleep(first_wait)
            first_wait = gs.HINT_INTERVAL
            room = get_room_state(room_code)
            if not room or room.get('state') != 'playing' or not room.get('game_state'):
                return
            gs = room['game_state']
            if gs.state_version != version or gs.stage != 'revealing':
                return
            revealed = gs.reveal_next_hint()
            version = gs.state_version
            if not revealed or gs.hints_done:
                # آخر معلومة: نافذة أخيرة ثم كشف الإجابة والانتقال
                final_wait = gs.FINAL_WINDOW
                await _emit_reveal_state(room_code, gs, extra={
                    'hintsJustCompleted': True, 'windowSeconds': final_wait})
                gs.reveal_started_at = time.time()
                gs.reveal_wait = final_wait
                await asyncio.sleep(final_wait)
                room = get_room_state(room_code)
                if not room or not room.get('game_state'):
                    return
                gs = room['game_state']
                if gs.stage == 'revealing' and gs.state_version == version:
                    await _reveal_and_advance(room_code)
                return
            await _emit_reveal_state(room_code, gs, extra={
                'windowSeconds': gs.HINT_INTERVAL})

    async def _start_character(room_code, advance=True):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if room.get('state') == 'finished' or gs.stage == 'finished':
            return
        if advance and gs.char_index >= gs.TOTAL_CHARACTERS and not gs.tiebreaker:
            await _resolve_end(room_code)
            return
        char = _pick_character(gs.used_char_ids)
        if not char:
            await _resolve_end(room_code, forced=True)
            return
        gs.start_new_character(char, advance_index=advance)
        await sio.emit('whoami_new_character', {
            'category': '',  # 🙈 حصرية لمساعدة كشف الفئة
            'totalHints': len(char.get('hints', [])),
            'scores': gs.scores, 'charIndex': gs.char_index,
            'totalCharacters': gs.TOTAL_CHARACTERS, 'tiebreaker': gs.tiebreaker,
        }, room=room_code)
        await _emit_reveal_state(room_code, gs, extra={
            'windowSeconds': gs.HINT_INTERVAL})
        sio.start_background_task(_reveal_loop, room_code, gs.state_version)

    _advancing = set()   # منع الانتقال المزدوج للشخصية التالية

    async def _reveal_and_advance(room_code):
        """يكشف الإجابة (لم يعرفها أحد أو خرج الطرفان) وينتقل للتالية."""
        if room_code in _advancing:
            return
        _advancing.add(room_code)
        try:
            room = get_room_state(room_code)
            if room and room.get('game_state'):
                gs = room['game_state']
                await sio.emit('whoami_reveal_answer', {
                    'name': (gs.current or {}).get('name', ''),
                    'scores': gs.scores,
                }, room=room_code)
                await asyncio.sleep(2.2)
            room = get_room_state(room_code)
            if not room or not room.get('game_state'):
                return
            gs = room['game_state']
            if gs.char_index >= gs.TOTAL_CHARACTERS and not gs.tiebreaker:
                await _resolve_end(room_code)
            else:
                await _start_character(room_code, advance=True)
        finally:
            _advancing.discard(room_code)

    async def _resolve_end(room_code, forced=False):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if gs.is_tie() and not forced:
            # تعادل: شخصيات حسم إضافية حتى ينكسر
            gs.tiebreaker = True
            await sio.emit('whoami_tiebreaker', {'scores': gs.scores}, room=room_code)
            await asyncio.sleep(1.5)
            await _start_character(room_code, advance=True)
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
                    # مكافآت الفائز/الخاسر كبقية الألعاب (عدا حروف) — في thread
                    await asyncio.to_thread(
                        record_match_result, wp, lp, 'whoami',
                        extra={'friendly': room.get('type') == 'friendly',
                               'winner_score': gs.scores.get(winner_sid, 0)})
                except Exception as e:
                    print(f" [whoami] خطأ تسجيل: {e}")
                # مباراة مكتملة بشرف للطرفين — تعافي سمعة الانسحاب
                try:
                    from app.domains.games.leaver_penalty import record_clean_match
                    for _uid in (room.get('user_ids') or {}).values():
                        record_clean_match(_uid)
                except Exception:
                    pass
        await sio.emit('whoami_match_over', {'winner': winner_sid, 'scores': gs.scores},
                       room=room_code)

    # ================= أحداث اللاعبين =================

    @sio.event
    async def whoami_start(sid, data):
        """للغرف الخاصة فقط — العامة تبدأ تلقائياً من room_events."""
        room_code = (data or {}).get('roomCode')
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if gs.stage != 'waiting':
            return
        if room.get('type') == 'public':
            return
        await _start_character(room_code, advance=True)

    @sio.event
    async def whoami_buzz(sid, data):
        room_code = (data or {}).get('roomCode')
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return
        gs = room['game_state']
        if not gs.can_buzz(sid):
            return
        started = getattr(gs, 'reveal_started_at', None)
        wait = getattr(gs, 'reveal_wait', gs.HINT_INTERVAL)
        if started is not None:
            elapsed = time.time() - started
            gs.reveal_remaining = max(0.5, wait - elapsed)
        else:
            gs.reveal_remaining = gs.HINT_INTERVAL
        gs.buzz_extra = 0
        gs.register_buzz(sid)
        await sio.emit('whoami_buzzed', {
            'sid': sid, 'answerWindow': gs.ANSWER_WINDOW,
            'pointsIfAnswer': gs.score_for_current(sid),
        }, room=room_code)
        sio.start_background_task(_answer_timeout, room_code, gs.state_version, sid)

    async def _answer_timeout(room_code, version, buzzer_sid):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        await asyncio.sleep(gs.ANSWER_WINDOW + getattr(gs, 'buzz_extra', 0))
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        # version يتغيّر عند «تمديد الجرس» فيُلغى هذا المؤقّت ويحلّ محلّه الجديد
        if gs.stage == 'buzzed' and gs.buzzed_player == buzzer_sid and gs.state_version == version:
            await _handle_strike(room_code, buzzer_sid, timed_out=True)

    @sio.event
    async def whoami_submit_answer(sid, data):
        room_code = (data or {}).get('roomCode')
        answer = ((data or {}).get('answer') or '').strip()
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return
        gs = room['game_state']
        if gs.stage != 'buzzed' or gs.buzzed_player != sid:
            return
        # الإرسال يلتزم: نبطل مؤقّت النافذة فوراً (بالإصدار) قبل التحكيم
        gs.bump_version()
        correct_name = (gs.current or {}).get('name', '')
        accepted = (gs.current or {}).get('accepted_answers', [])
        result = check_answer(answer, correct_name, accepted, None)
        is_correct = result['verdict'] == 'accept'
        if result.get('verdict') == 'maybe':
            # الحالة الحدّية: الحكم الذكي — وعند الفشل نرفض (لا نقاط بالخطأ)
            try:
                await sio.emit('whoami_judging', {'sid': sid}, room=room_code)
                from app.infrastructure.ai_judge import judge_answer
                hints = (gs.current or {}).get('hints', [])
                judged = await judge_answer(
                    f"شخصية وصفها: {hints}", correct_name, answer, timeout=2.0)
                is_correct = bool(judged.get('accept', False))
            except Exception:
                is_correct = False
        if is_correct:
            points = gs.score_for_current(sid)
            gs.award(sid, points)
            await sio.emit('whoami_answer_result', {
                'sid': sid, 'correct': True, 'points': points,
                'name': correct_name, 'scores': gs.scores,
            }, room=room_code)
            await asyncio.sleep(1.8)
            room = get_room_state(room_code)
            if not room or not room.get('game_state'):
                return
            gs = room['game_state']
            if gs.char_index >= gs.TOTAL_CHARACTERS and not gs.tiebreaker:
                await _resolve_end(room_code)
            elif gs.tiebreaker and not gs.is_tie():
                await _resolve_end(room_code)
            else:
                await _start_character(room_code, advance=True)
        else:
            await _handle_strike(room_code, sid, timed_out=False)

    async def _handle_strike(room_code, sid, timed_out):
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        # «درع السترايك»: يمتص أول خطأ في الشخصية الحالية (خارج كسر التعادل)
        if gs.consume_shield_if_active(sid):
            await sio.emit('whoami_shield_absorbed', {
                'sid': sid, 'name': _name_of(room, sid),
                'timedOut': timed_out, 'shield_active': gs.shield_active,
            }, room=room_code)
            resume = gs.reveal_remaining if gs.reveal_remaining is not None else gs.HINT_INTERVAL
            gs.stage = 'revealing'
            gs.buzzed_player = None
            gs.bump_version()
            await asyncio.sleep(0.9)
            await _emit_reveal_state(room_code, gs, extra={
                'resumed': True, 'resumeSeconds': resume})
            if gs.hints_done:
                gs.reveal_started_at = time.time()
                gs.reveal_wait = resume
                _v = gs.state_version
                await asyncio.sleep(resume)
                r2 = get_room_state(room_code)
                if r2 and r2.get('game_state'):
                    g2 = r2['game_state']
                    if g2.stage == 'revealing' and g2.state_version == _v:
                        await _reveal_and_advance(room_code)
            else:
                sio.start_background_task(_reveal_loop, room_code, gs.state_version, resume)
            return
        strikes = gs.add_strike(sid)
        await sio.emit('whoami_strike', {
            'sid': sid, 'strikes': gs.strikes, 'timedOut': timed_out,
            'count': strikes, 'maxStrikes': gs.MAX_STRIKES,
        }, room=room_code)
        if gs.both_struck_out():
            await _reveal_and_advance(room_code)
            return
        # استئناف الكشف بما تبقى من فاصل المعلومة
        resume = gs.reveal_remaining if gs.reveal_remaining is not None else gs.HINT_INTERVAL
        gs.stage = 'revealing'
        gs.buzzed_player = None
        gs.bump_version()
        await _emit_reveal_state(room_code, gs, extra={
            'resumed': True, 'resumeSeconds': resume})
        if gs.hints_done:
            # النافذة الأخيرة: استئنافها ثم كشف وانتقال
            gs.reveal_started_at = time.time()
            gs.reveal_wait = resume
            _v = gs.state_version
            await asyncio.sleep(resume)
            room = get_room_state(room_code)
            if room and room.get('game_state'):
                gs = room['game_state']
                if gs.stage == 'revealing' and gs.state_version == _v:
                    await _reveal_and_advance(room_code)
        else:
            sio.start_background_task(_reveal_loop, room_code, gs.state_version, resume)

    @sio.event
    async def whoami_use_help(sid, data):
        """استخدام مساعدة في «من أنا». data: { roomCode, helpId, token }

        كل مساعدة مرة واحدة بالمباراة، تُستهلك من المخزون (وضع التطوير بلا
        استهلاك). لا مساعدة تكشف المعلومة التالية مبكراً (منع Pay-to-Win).
        توقيت 'revealing' = أثناء الكشف قبل جرسك؛ 'buzzed' = بعد جرسك.
        """
        from app.domains.games.whoami.helps import get_help
        from app.domains.games.core_manager import _allow_same_ip
        from app.core.anticheat import check_action_rate
        room_code = (data or {}).get('roomCode')
        help_id = (data or {}).get('helpId')
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return
        gs = room['game_state']
        if not gs.is_player_in_game(sid):
            return
        if check_action_rate(sid, 'whoami_use_help', max_per_second=1):
            return
        h = get_help(help_id)
        if not h:
            await sio.emit('whoami_help_result', {'ok': False, 'msg': 'مساعدة غير معروفة'}, to=sid)
            return

        # بوابة التوقيت
        timing = h.get('timing', 'revealing')
        if timing == 'buzzed':
            # تُستخدم بعد جرسك أنت فقط، وقبل انتهاء نافذتك
            if gs.stage != 'buzzed' or gs.buzzed_player != sid:
                await sio.emit('whoami_help_result',
                               {'ok': False, 'msg': 'تُستخدم بعد ضغطك الجرس'}, to=sid)
                return
        else:  # revealing
            if gs.stage != 'revealing':
                await sio.emit('whoami_help_result',
                               {'ok': False, 'msg': 'تُستخدم أثناء عرض المعلومات'}, to=sid)
                return

        if gs.help_used(sid, help_id):
            await sio.emit('whoami_help_result',
                           {'ok': False, 'msg': 'استخدمتها في هذه المباراة'}, to=sid)
            return

        # شروط خاصة قبل الاستهلاك
        if help_id in ('w_strike_shield', 'w_lock_points') and gs.in_tiebreak():
            await sio.emit('whoami_help_result',
                           {'ok': False, 'msg': 'لا تعمل في جولات كسر التعادل'}, to=sid)
            return
        if help_id == 'w_strike_shield' and gs.shield_active.get(sid, False):
            await sio.emit('whoami_help_result',
                           {'ok': False, 'msg': 'درعك مفعّل بالفعل'}, to=sid)
            return
        if help_id == 'w_lock_points' and gs.locked_points.get(sid) is not None:
            await sio.emit('whoami_help_result',
                           {'ok': False, 'msg': 'النقاط مقفولة بالفعل'}, to=sid)
            return

        # الاستهلاك من المخزون (وضع التطوير = بلا استهلاك)
        dev_mode = _allow_same_ip()
        sender = next((p for p in room['players'] if p.get('sid') == sid), None)
        user_id = sender.get('user_id') if sender else None
        if not dev_mode and user_id:
            from app.domains.wallet.help_inventory import consume_help
            if not consume_help(user_id, help_id):
                await sio.emit('whoami_help_result',
                               {'ok': False, 'msg': 'لا تملك هذه المساعدة'}, to=sid)
                return

        current = gs.current or {}

        # ===== التأثيرات =====
        if help_id == 'w_extend_buzz':
            extra = int((h.get('params') or {}).get('seconds', 5))
            gs.buzz_extra += extra
            version = gs.bump_version()   # يُبطل مؤقّت النافذة القديم
            new_window = gs.ANSWER_WINDOW + gs.buzz_extra
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': f'⏱️ +{extra} ثوانٍ لنافذتك!'}, to=sid)
            await sio.emit('whoami_buzz_extended', {
                'sid': sid, 'newWindow': new_window, 'added': extra,
            }, room=room_code)
            # مؤقّت جديد بديل بحارس الإصدار
            async def _extended():
                await asyncio.sleep(new_window)
                r2 = get_room_state(room_code)
                if not r2 or not r2.get('game_state'):
                    return
                g2 = r2['game_state']
                if g2.stage == 'buzzed' and g2.buzzed_player == sid and g2.state_version == version:
                    await _handle_strike(room_code, sid, timed_out=True)
            sio.start_background_task(_extended)
            return

        if help_id == 'w_reveal_category':
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': f'🏷️ المجال: {current.get("category", "؟")}'}, to=sid)
            return

        if help_id == 'w_reveal_era':
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': f'🎂 الحقبة: {current.get("era", "غير محددة")}'}, to=sid)
            return

        if help_id == 'w_first_letter':
            name = (current.get('name') or '').strip()
            first = name[0] if name else '؟'
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': f'🔤 يبدأ اسمها بحرف "{first}"'}, to=sid)
            return

        if help_id == 'w_half_name':
            name = (current.get('name') or '').strip()
            first = name[0] if name else '؟'
            last = name[-1] if name else '؟'
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': f'🎯 يبدأ بـ"{first}" وينتهي بـ"{last}"'}, to=sid)
            return

        if help_id == 'w_strike_shield':
            gs.shield_active[sid] = True
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': '🛡️ درعك مفعّل — أول خطأ لن يُحسب'}, to=sid)
            await sio.emit('whoami_shield_on', {
                'sid': sid, 'shield_active': gs.shield_active}, room=room_code)
            return

        if help_id == 'w_lock_points':
            gs.lock_points_for(sid)
            locked = gs.locked_points[sid]
            gs.mark_help_used(sid, help_id)
            await sio.emit('whoami_help_result', {
                'ok': True, 'helpId': help_id,
                'info': f'🔒 ثبّتّ نقاطك على {locked} — لن تنقص!'}, to=sid)
            return

    @sio.event
    async def whoami_surrender(sid, data):
        room_code = (data or {}).get('roomCode')
        room = get_room_state(room_code)
        if not room or not room.get('game_state'):
            return
        gs = room['game_state']
        if not gs.is_player_in_game(sid) or gs.stage == 'finished':
            return
        winner_sid = gs.opponent(sid)
        gs.stage = 'finished'
        room['state'] = 'finished'
        wp = next((p for p in room['players'] if p['sid'] == winner_sid), None)
        lp = next((p for p in room['players'] if p['sid'] == sid), None)
        if wp and lp:
            try:
                # المنسحب لا يأخذ مكافأة الفوز — الفائز يُسجَّل كبقية الألعاب
                await asyncio.to_thread(
                    record_match_result, wp, lp, 'whoami',
                    extra={'friendly': room.get('type') == 'friendly',
                           'surrender': True,
                           'winner_score': gs.scores.get(winner_sid, 0)})
            except Exception as e:
                print(f" [whoami] خطأ تسجيل انسحاب: {e}")
        await sio.emit('whoami_match_over', {
            'winner': winner_sid, 'scores': gs.scores, 'surrender': True,
        }, room=room_code)

    # ============ الإيموجيات (نفس نمط بقية الألعاب) ============
    @sio.event
    async def whoami_send_emoji(sid, data):
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
        if check_action_rate(sid, 'whoami_send_emoji', max_per_second=1):
            return
        opp = gs.opponent(sid)
        await sio.emit('whoami_emoji', {'emojiId': emoji_id, 'isMine': True}, to=sid)
        await sio.emit('whoami_emoji', {'emojiId': emoji_id, 'isMine': False}, to=opp)

    @sio.event
    async def whoami_get_my_emojis(sid, data):
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
        await sio.emit('whoami_my_emojis', {'owned': owned}, to=sid)

    # ربط دالة البدء بالمرجع العام (تُستدعى من room_events)
    _start_first_character = _start_character


async def send_whoami_reconnect_state(sio, room_code: str, sid: str):
    """يرسل حالة المباراة الحالية للاعب العائد بعد انقطاع."""
    room = get_room_state(room_code)
    if not room or not room.get('game_state'):
        return
    gs = room['game_state']
    if gs.stage in ('waiting', 'finished'):
        return
    payload = {
        'reconnect': True,
        'stage': gs.stage,
        'hints': gs.revealed_hints(),
        'category': '',  # 🙈 حصرية لمساعدة كشف الفئة
        'hintsDone': gs.hints_done,
        'revealedCount': gs.revealed_count,
        'totalHints': len((gs.current or {}).get('hints', [])),
        'scores': gs.scores, 'strikes': gs.strikes,
        'pointsIfAnswer': gs.score_for_current(sid),
        'charIndex': gs.char_index, 'totalCharacters': gs.TOTAL_CHARACTERS,
        'tiebreaker': gs.tiebreaker,
        'buzzedPlayer': gs.buzzed_player,
        'helps_used': {k: list(v) for k, v in gs.helps_used.items()},
        'shield_active': gs.shield_active,
        'locked_points': gs.locked_points,
    }
    await sio.emit('whoami_reveal_state', payload, to=sid)
