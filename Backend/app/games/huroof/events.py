import asyncio
import html
import random
import json
import time

# ==========================================
# 🔄 الاستيرادات من الهيكلة الجديدة (تأكد من مطابقتها لمساراتك)
# ==========================================
from app.core.database import SessionLocal, Question, User
from app.games.core_manager import get_room_state, rooms
from app.services.reward_service import record_match_result
from app.services.telegram_bot import send_secret_to_mobile

# ==========================================
# 🚀 كاش أسئلة حروف بالذاكرة (إصلاح bottleneck حرج)
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
            rows.append({
                'id': q.id,
                'question_text': q.question_text,
                'correct_answer': q.correct_answer,
                'category': q.category,
                'accepted_answers': extra.get('accepted_answers', []),
                'letter_extra': normalize_letter(extra.get('letter', '') or ''),
                'letter_ans': normalize_letter(core[0]) if core else '',
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
        print(f"⚠️ [huroof] mark seen: {e}")


# 🔌 المرحلة ب: نقطة الدخول الموحّدة للتحقق من أفعال اللاعب (BaseGame)
def _get_huroof_game():
    """يجلب نسخة HuroofGame المسجّلة في الإطار (للتحقق الموحّد)."""
    try:
        from app.games.base import GameRegistry
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

# 🔤 معالج النصوص العربية (Normalize → Fuzzy → Token)
from app.core.text_processor import check_answer

# 🛡️ Anti-Cheat (server-side validation)
from app.core.anticheat import (
    check_action_rate, check_human_reaction, check_payload_safety,
    validate_huroof_buzz, validate_huroof_answer,
    report_violation, is_temp_banned, Severity,
)

# 💡 ملاحظة هامة: القواميس العالمية مثل connected_players يجب أن تكون في ملف مشترك (مثلاً app/sockets/state.py)
from app.sockets.state import connected_players, disconnect_timers
# 💡 دالة العودة للوبي يجب أن تكون في ملف اللوبي
from app.sockets.lobby import return_players_to_lobby

# ==========================================
# 🛠️ الفلاتر والدوال المساعدة للعبة حروف
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

def clean_text_for_match(t):
    """فلتر تنظيف النصوص للتحكيم اللحظي"""
    t = str(t).strip()
    t = t.replace("ال", "", 1) if t.startswith("ال") else t
    return t.replace(" ", "").replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

def check_answer_fast_track(player_ans, correct_ans, accepted_list, required_letter):
    """التحكيم اللحظي (0 ملي ثانية) - 3 فلاتر"""
    p_clean = clean_text_for_match(player_ans)
    req_clean = clean_text_for_match(required_letter)
    
    # 1. فلتر الإعدام الفوري (الكلمة لا تبدأ بالحرف المطلوب)
    if not p_clean.startswith(req_clean):
        return False, "wrong_letter"
        
    # 2. فلتر الفوز الفوري (تطابق مع الإجابة الرسمية)
    c_clean = clean_text_for_match(correct_ans)
    if p_clean == c_clean:
        return True, "exact_match"
        
    # 3. فلتر الفوز الفوري (تطابق مع قائمة المرادفات المسموحة)
    for acc in accepted_list:
        if p_clean == clean_text_for_match(acc):
            return True, "accepted_match"
            
    # 4. إذا مرت من كل هذا، نحيلها للمحكمة العليا (الذكاء الاصطناعي)
    return False, "إجابة خاطئة"


# ==========================================
# 🎮 تسجيل أحداث السوكيت للعبة حروف
# ==========================================
def register_huroof_events(sio):
    """تغليف الدوال والأحداث لكي تتمكن من استخدام كائن sio"""

    async def emit_turn_changed(room_code, gs, turn_sid):
        """يبثّ تغيّر الدور بـ sid + اللون (اللون أكثر استقراراً عبر إعادة الاتصال)."""
        turn_color = 'green' if turn_sid == gs.p1 else 'orange'
        await sio.emit('huroof_turn_changed',
                       {'turn_sid': turn_sid, 'turn_color': turn_color},
                       room=room_code)

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
        # 🎯 نسجّل بيانات المؤقّت النشط (لمساعدة تمديد الوقت)
        _room0 = get_room_state(room_code)
        if _room0 and _room0.get('game_state'):
            import time as _t
            _room0['game_state'].active_timer = {
                'version': version, 'timeout_type': timeout_type,
                'ends_at': _t.time() + seconds
            }
        await asyncio.sleep(seconds)
        # 🕵️ رادار: هل الغرفة لا تزال موجودة وبحالة لعب؟
        room = get_room_state(room_code)
        if not room or room.get('state') != 'playing' or not room.get('game_state'):
            return 
            
        gs = room['game_state']
        if gs.state_version != version: return
        
        # التحقق أن الحالة لم تتغير
        if gs.state_version == version:
            print(f"⏰ [Timeout] الغرفة {room_code} | النوع: {timeout_type}")
            
            if timeout_type == 'timeout_buzz_r1':
                # 0️⃣ لم يضغط أحد الجرس في الـ 40 ثانية -> فرصة أخيرة مباشرة
                gs.attempts = 2
                version = advance_state(gs, 'question')
                gs.buzzed_player = None
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')

            elif timeout_type == 'timeout_answer_r1':
                # 1️⃣ اللاعب الأول أضاع الـ 15 ثانية -> ينتقل للخصم بـ 20 ثانية (المحاولة الأولى)
                version = advance_state(gs, 'answer_r2')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 20, 'round': 'r2'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
                
            elif timeout_type == 'timeout_answer_r2':
                # 2️⃣ الخصم أضاع الـ 20 ثانية -> فشل الكل في الأولى، نفتح المحاولة الثانية
                gs.attempts = 2 
                version = advance_state(gs, 'question') 
                gs.buzzed_player = None
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')
                
            elif timeout_type == 'timeout_answer_r3':
                # 3️⃣ اللاعب أضاع الـ 12 ثانية (في المحاولة الثانية) -> ينتقل للخصم بـ 12 ثانية
                version = advance_state(gs, 'answer_r4')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 12, 'round': 'r4'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')

            elif timeout_type == 'timeout_answer_r4' or timeout_type == 'timeout_buzz_r3':
                # 4️⃣ انتهت كل الفرص أو لم يضغط أحد في الفرصة الثانية
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

        # 🚀 كل عمل DB صار في threads (asyncio.to_thread) — لا يحجب event loop:
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
        valid_qs = [
            q for q in all_qs
            if q['id'] not in used and q['id'] not in combined_seen
            and (q['letter_extra'] == norm_letter or q['letter_ans'] == norm_letter)
        ]

        if not valid_qs:
            print(f"⚠️ نفدت الأسئلة الجديدة لحرف '{norm_letter}' بالنسبة لهذين اللاعبَين.")
            fallback = {
                "question": f"نفدت الأسئلة الجديدة لحرف ({norm_letter}) لكلاكما. اختاروا حرفاً آخر.",
                "answer": "لا يوجد",
                "category": "نفدت الأسئلة",
                "letter": norm_letter,
                "accepted_answers": []
            }
            await sio.emit('receive_ai_question', fallback, room=room_code)
            return

        # 📚 اختيار التصنيف: لو اللاعب صاحب الدور اختار تصنيفاً مسبقاً، نُفضّله
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

        # 📝 تسجيل المشاهدة fire-and-forget — لا نؤخر وصول السؤال للاعبين
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

        # 🛡️ ANTI-CHEAT: track when question was shown for reaction time validation
        gs.question_shown_at = time.time()

        asyncio.create_task(send_secret_to_mobile(gs.current_question['question'], gs.current_question['answer']))

        await sio.emit('huroof_new_question', {
            'questionData': gs.current_question,
            'round': 'r1',
            'timer': 40,
            'changed': is_change
        }, room=room_code)

        sio.start_background_task(huroof_timer_task, room_code, version, 40, 'timeout_buzz_r1')

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

                        # 🛡️ معامل مكافحة التواطؤ من user_ids الغرفة
                        from app.services.anti_collusion import get_reward_multiplier
                        uids = list((room.get('user_ids') or {}).values())
                        mult = get_reward_multiplier(uids[0], uids[1]) if len(uids) == 2 else 1.0

                        # 🚀 في thread — لا يحجب event loop
                        await asyncio.to_thread(
                            record_match_result, winner_player, loser_player,
                            room.get('game_mode', 'huroof'), extra={
                                'winner_rounds': gs.points[player_color],
                                'loser_rounds':  gs.points[loser_color],
                                'collusion_multiplier': mult,
                                'friendly': room.get('type') == 'friendly',
                            })

                        # 🚪 مباراة مكتملة بشرف للطرفين → تعافي السمعة
                        from app.services.leaver_penalty import record_clean_match
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
                            print(f"🗑️ تم حذف الغرفة {room_code} بعد انتهاء المباراة.")
                    
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
            else:
                advance_state(gs, 'selecting')
                gs.turn = sid
                await asyncio.sleep(2) 
                await emit_turn_changed(room_code, gs, sid)
                
        else:
            # 🎯 الإجابة الصحيحة تُكشف فقط عند انتهاء السؤال للطرفين
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
                
            elif gs.stage == 'answer_r2':
                # نهاية المرحلة الأولى → الفرصة الأخيرة (نفس السؤال). لا نكشف الإجابة بعد.
                gs.attempts = 2
                version = advance_state(gs, 'question') 
                gs.buzzed_player = None
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code) 
                
            elif gs.stage == 'answer_r3':
                version = advance_state(gs, 'answer_r4')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 12, 'round': 'r4'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')
                
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
        
        # 🔌 تحقق موحّد (BaseGame) + التحقق الموجود
        if not _action_allowed(gs, sid, 'select_hex'):
            return
        if gs.stage != 'selecting' or not is_players_turn(room, gs, sid):
            return 
            
        gs.active_hex = gs.board[hex_index]
        await sio.emit('huroof_hex_locked', {'hexIndex': hex_index, 'letter': gs.active_hex['letter']}, room=room_code)
        
        await trigger_new_question(room_code)

    @sio.event
    async def huroof_buzz(sid, data):
        # 🛡️ ANTI-CHEAT: payload safety
        payload_issue = check_payload_safety(data)
        if payload_issue:
            await report_violation(sid, sio, payload_issue, severity=Severity.HIGH)
            return

        # 🛡️ temp ban check
        if is_temp_banned(sid):
            return

        # 🛡️ rate limiting (لا أحد يضغط buzz أكثر من 5/ثانية بشري)
        rate_issue = check_action_rate(sid, 'huroof_buzz', max_per_second=5)
        if rate_issue:
            await report_violation(sid, sio, rate_issue, severity=Severity.HIGH)
            return

        room_code = data.get('roomCode')
        if not isinstance(room_code, str) or len(room_code) > 20:
            await report_violation(sid, sio, "invalid_room_code", severity=Severity.MEDIUM)
            return

        room = get_room_state(room_code)

        # 🛡️ ANTI-CHEAT: validate buzz state
        buzz_issue = validate_huroof_buzz(sid, room, connected_players)
        if buzz_issue:
            await report_violation(sid, sio, buzz_issue, severity=Severity.HIGH)
            return

        if not room or not room.get('game_state'): return
        gs = room['game_state']

        allowed_stages = ['question', 'buzz_r1', 'buzz_r3']
        if gs.stage not in allowed_stages:
            print(f"⚠️ تجاهل الضغطة: المرحلة الحالية هي {gs.stage}")
            return

        # 🛡️ ANTI-CHEAT: human reaction time check
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
        # 🛡️ ANTI-CHEAT: payload safety (very important - answer is user input)
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

        # 🛡️ length limit on answer (no novels)
        if len(player_ans) > 200:
            await report_violation(sid, sio, f"oversized_answer:{len(player_ans)}",
                                    severity=Severity.MEDIUM)
            return

        room = get_room_state(room_code)
        if not room: return
        gs = room['game_state']

        # 🛡️ ANTI-CHEAT: validate answer state
        answer_issue = validate_huroof_answer(sid, room, gs.buzzed_player)
        if answer_issue:
            await report_violation(sid, sio, answer_issue, severity=Severity.HIGH)
            return

        if gs.stage not in ['answer_r1', 'answer_r2', 'answer_r3', 'answer_r4']: return
        if sid != gs.buzzed_player: return

        # 🛡️ الإرسال يلتزم: نبطل مؤقّت الإجابة فوراً (بالإصدار) —
        # يمنع انفجار المهلة أثناء تحكيم AI (≤2ث) ومعالجة النتيجة مرتين.
        gs.state_version += 1

        correct_ans = gs.current_question['answer']
        accepted_list = gs.current_question['accepted_answers']
        req_letter = gs.current_question['letter']

        # 🔤 المعالج: Normalize → Fuzzy → Token analysis (فوري — يحل ~97%)
        result = check_answer(player_ans, correct_ans, accepted_list, req_letter)
        is_correct = result['verdict'] == 'accept'

        # ⚖️ الطبقة 4 (AI Judge) — فقط للحالات الحدّية النادرة 'maybe'
        # ⚡ مع timeout صارم + تساهل افتراضي (لا يُبطئ اللعبة).
        if result.get('verdict') == 'maybe':
            try:
                from app.core.ai_judge import judge_answer
                judged = await judge_answer(
                    gs.current_question.get('text', '') or correct_ans,
                    correct_ans, player_ans, timeout=2.0
                )
                is_correct = judged.get('accept', True)
                result['ai_source'] = judged.get('source')
            except Exception:
                # أي خطأ → متساهل (نعطي اللاعب الفائدة عند الشك)
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
            
            if len(gs.skip_votes) >= 2:
                # 🆕 نكشف الإجابة الصحيحة للطرفين قبل تغيير السؤال (اتفقا على التغيير)
                correct_answer = ''
                if gs.current_question:
                    correct_answer = gs.current_question.get('answer', '')
                if correct_answer:
                    await sio.emit('huroof_reveal_answer', {'correct_answer': correct_answer}, room=room_code)
                    await asyncio.sleep(2)
                await sio.emit('huroof_timeout_info', {'msg': 'تم الاتفاق! جاري جلب سؤال جديد...'}, room=room_code)
                gs.state_version += 1 
                await trigger_new_question(room_code, is_change=True)

    @sio.event
    async def huroof_use_help(sid, data):
        """🎯 استخدام مساعدة. data: { roomCode, helpId }
        قواعد: المساعدة مُفعّلة + لم تُستخدم من قبل (مرة واحدة في المباراة) +
        اللاعب في الوضع الصحيح للمساعدة."""
        from app.games.huroof.helps import is_valid_help, get_help

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

        # 🎒 نحصل على user_id ووضع التطوير (للمخزون)
        from app.games.core_manager import _allow_same_ip
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

        # 🎒 4) يملك المساعدة في مخزونه؟ (إلا في وضع التطوير)
        if not dev_mode and user_id:
            from app.services.help_inventory import get_quantity
            if get_quantity(user_id, help_id) <= 0:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'لا تملك هذه المساعدة — اشترها من المتجر'}, to=sid)
                return

        # 5) 🔑 بوابة التوقيت حسب نوع المساعدة:
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

        # 🎒 نستهلك من المخزون (إلا في وضع التطوير) — قبل التنفيذ
        if not dev_mode and user_id:
            from app.services.help_inventory import consume_help
            if not consume_help(user_id, help_id):
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'نفد رصيدك من هذه المساعدة'}, to=sid)
                return

        # ===== تنفيذ كل مساعدة =====

        # ⏱️ تمديد الوقت: نعيد تشغيل المؤقّت النشط بثوانٍ إضافية (خادمياً — فعّال حقاً)
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

        # 🔄 تغيير السؤال: نجلب سؤالاً جديداً لنفس الحرف
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

        # 🔢 كاشف عدد الحروف: نحسب طول الإجابة ونرسله لصاحب المساعدة فقط
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

        # 🔍 كاشف الحرف الثاني: الحرف الذي يلي المختار
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

        # 🎯 كاشف آخر حرف
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

        # 🏷️ تلميح التصنيف
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

        # 🎲 كاشف حرف وسطي: نكشف حرفاً واحداً من وسط الإجابة (تلميح خفيف)
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

        # ❄️ تجميد المؤقّت: نمدّد المؤقّت 5 ثوانٍ (نفس آلية تمديد الوقت)
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

        # ⏭️ تخطّي الحرف: نعيد اللاعب لاختيار حرف آخر (يلغي السؤال الحالي بلا عقوبة)
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

        # 📚 اختيار التصنيف (قبل الحرف): يحفظ تصنيفاً مفضّلاً لسؤالك القادم
        if help_id == 'choose_category':
            chosen_cat = (data.get('category') or '').strip()
            # قائمة التصنيفات المتاحة (من قاعدة الأسئلة)
            from app.models.user import Question
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
                    from app.services.help_inventory import add_help
                    add_help(user_id, help_id, 1)
                return
            if cats and chosen_cat not in cats:
                await sio.emit('huroof_help_result', {'ok': False, 'msg': 'تصنيف غير متاح'}, to=sid)
                if not dev_mode and user_id:
                    from app.services.help_inventory import add_help
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
        from app.games.huroof.helps import (get_enabled_catalog, DEFAULT_LOADOUT,
                                             get_slots_for_player, FOURTH_SLOT_LEVEL, FOURTH_SLOT_ITEM)
        from app.games.core_manager import _allow_same_ip
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
                from app.services.help_inventory import get_inventory, grant_starter_helps_once
                grant_starter_helps_once(user_id)  # هدية البداية للاعب الجديد
                inventory = get_inventory(user_id)
                # نجلب مستوى اللاعب لحساب الخانات
                try:
                    from app.models.user import User
                    from app.core.database import SessionLocal
                    _db = SessionLocal()
                    _u = _db.query(User).filter(User.id == user_id).first()
                    player_level = (_u.level if _u else 0) or 0
                    _db.close()
                except Exception:
                    player_level = 0
                from app.services.cosmetics import owns_cosmetic
                owns_fourth = owns_cosmetic(user_id, FOURTH_SLOT_ITEM)
                slots = get_slots_for_player(player_level, owns_fourth)
                try:
                    from app.services.loadout import get_loadout
                    _saved_loadout = get_loadout(user_id, player_level)
                except Exception:
                    _saved_loadout = None
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
                    from app.services.cosmetics import get_owned_cosmetics
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
            from app.services.anti_collusion import get_reward_multiplier
            uids = list((room.get('user_ids') or {}).values())
            mult = get_reward_multiplier(uids[0], uids[1]) if len(uids) == 2 else 1.0
            await asyncio.to_thread(
                record_match_result, winner_player, loser_player, room.get('game_mode', 'huroof'),
                extra={'reason': 'surrender', 'collusion_multiplier': mult,
                       'friendly': room.get('type') == 'friendly'})

            # 🚪 عقوبة الانسحاب المتكرر (للمنسحب) + مكافأة الفائز (سلوك جيد)
            # 🤝 المباريات الودية لا تُطبّق عقوبة انسحاب (صفر مخاطر)
            is_friendly = room.get('type') == 'friendly'
            user_ids_map = room.get('user_ids') or {}
            loser_uid = user_ids_map.get(sid)
            winner_uid = user_ids_map.get(winner_player['sid']) if winner_player else None
            from app.services.leaver_penalty import record_leave, record_clean_match
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
                print(f"🗑️ تم حذف الغرفة {room_code} نهائياً من الذاكرة.")
        
    @sio.event
    async def join_party_mode(sid, data):
        # 💡 تم استيراد المتغيرات من ملف الحالة المركزية (سننشئه في الخطوة التالية)
        from app.sockets.state import connected_players, party_session_used_ids
        import app.sockets.state as state # للوصول للمتغيرات وتعديلها
        
        game_mode = data.get('gameMode', 'huroof')
        player_name = data.get('name', 'لاعب')
        avatar = data.get('avatar', 'https://api.dicebear.com/7.x/bottts/svg?seed=Hero')
        
        connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': f"party_{game_mode}"}

        if state.party_session_sid is None:
            state.party_session_sid = sid
            state.party_session_used_ids = set()
        
        # 🛡️ إصلاح أمني: كان يبث connected_players.values() خاماً — يسرّب token/user_id للجميع!
        # الآن delta منظّف (بدون حقول داخلية) عبر نظام الحضور.
        from app.sockets.lobby import presence_delta
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

            # ✅ نبني قائمة الأسئلة المتاحة بعد استبعاد المستخدمة في هذه الجلسة
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
                # ✅ نحجز السؤال فوراً في سجل الجلسة قبل الإرسال
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
                # ♻️ نفدت كل أسئلة هذا الحرف في هذا التصنيف — نرسل رسالة للمستخدم
                print(f"⚠️ [Party] نفدت أسئلة حرف '{norm_letter}' بتصنيف '{requested_category}'.")
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
    # 🛡️ الإبلاغ عن الخصم (أثناء/بعد المباراة)
    # ==========================================
    @sio.event
    async def report_opponent(sid, data):
        """
        بلاغ عن الخصم. يُقبل فقط من لاعب فعلي في غرفة فعلية ضد الهدف.
        data: { roomCode, token, reason }
        """
        room_code = data.get('roomCode')
        token = data.get('token')
        reason = data.get('reason', 'other')

        room = get_room_state(room_code)
        if not room:
            await sio.emit('report_result', {'ok': False, 'msg': 'الغرفة غير موجودة'}, to=sid)
            return

        # المُبلّغ لازم يكون لاعباً في الغرفة
        reporter = next((p for p in room['players'] if p['sid'] == sid), None)
        target = next((p for p in room['players'] if p['sid'] != sid), None)
        if not reporter or not target:
            await sio.emit('report_result', {'ok': False, 'msg': 'لست في هذه المباراة'}, to=sid)
            return

        # نتحقق من هوية المُبلّغ عبر التوكن
        from app.sockets.auth_helper import verify_socket_token
        user, db = verify_socket_token(token)
        if not user:
            await sio.emit('report_result', {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
            return
        reporter_id = user.id
        db.close()

        # نجلب user_id الهدف من خريطة الغرفة
        user_ids = room.get('user_ids') or {}
        target_id = target.get('user_id') or user_ids.get(target['sid'])
        if not target_id:
            await sio.emit('report_result', {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
            return

        from app.services.player_reports import submit_report
        result = submit_report(
            reporter_id=reporter_id,
            target_id=target_id,
            reason=reason,
            room_code=room_code,
            game_mode=room.get('game_mode', 'huroof'),
        )
        await sio.emit('report_result', {'ok': result['ok'], 'msg': result['msg']}, to=sid)

    # ==========================================
    # 👥 الصداقة والحظر (من بروفايل الخصم)
    # ==========================================
    @sio.event
    async def friend_request_opponent(sid, data):
        """طلب صداقة للخصم. data: { roomCode, token }"""
        room = get_room_state(data.get('roomCode'))
        if not room:
            await sio.emit('friend_result', {'ok': False, 'msg': 'الغرفة غير موجودة'}, to=sid)
            return
        target = next((p for p in room['players'] if p['sid'] != sid), None)
        if not target:
            await sio.emit('friend_result', {'ok': False, 'msg': 'لا يوجد خصم'}, to=sid)
            return

        from app.sockets.auth_helper import verify_socket_token
        user, db = verify_socket_token(data.get('token'))
        if not user:
            await sio.emit('friend_result', {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
            return
        requester_id = user.id
        db.close()

        target_id = target.get('user_id') or (room.get('user_ids') or {}).get(target['sid'])
        if not target_id:
            await sio.emit('friend_result', {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
            return

        from app.services.friends import send_friend_request
        result = send_friend_request(requester_id, target_id)
        await sio.emit('friend_result', result, to=sid)
        # نُشعر الخصم بطلب وارد: إشعار دائم + دفع حي لو متصل
        if result['ok']:
            from app.services.notifications import add_notification, find_online_sid
            notif = add_notification(
                target_id, 'friend_request',
                f'أرسل لك {user.player_name} طلب صداقة',
                sender_id=requester_id
            )
            online_sid = find_online_sid(target_id)
            if online_sid and notif:
                await sio.emit('new_notification', notif, to=online_sid)
            # 🆕 toast تفاعلي لحظي للخصم داخل المباراة (غير معطّل)
            opp = next((p for p in room['players'] if p['sid'] != sid), None)
            if opp:
                await sio.emit('ingame_friend_request', {
                    'requesterId': requester_id,
                    'requesterName': user.player_name,
                }, to=opp['sid'])

    @sio.event
    async def remove_friend_opponent(sid, data):
        """حذف الخصم من الأصدقاء (في المباراة الودية). data: { roomCode, token }"""
        room = get_room_state(data.get('roomCode'))
        if not room:
            await sio.emit('friend_result', {'ok': False, 'msg': 'الغرفة غير موجودة'}, to=sid)
            return
        target = next((p for p in room['players'] if p['sid'] != sid), None)
        if not target:
            await sio.emit('friend_result', {'ok': False, 'msg': 'لا يوجد خصم'}, to=sid)
            return

        from app.sockets.auth_helper import verify_socket_token
        user, db = verify_socket_token(data.get('token'))
        if not user:
            await sio.emit('friend_result', {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
            return
        uid = user.id
        db.close()

        target_id = target.get('user_id') or (room.get('user_ids') or {}).get(target['sid'])
        if not target_id:
            await sio.emit('friend_result', {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
            return

        from app.core.database import engine
        from sqlalchemy import text
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    DELETE FROM friendships
                    WHERE status = 'accepted'
                      AND ((user_id = :a AND friend_id = :b) OR (user_id = :b AND friend_id = :a))
                """), {"a": uid, "b": target_id})
                conn.commit()
            await sio.emit('friend_result', {'ok': True, 'msg': 'تم حذف الصديق'}, to=sid)
            # 🆕 نُعلم الطرف الآخر أن الصداقة أُزيلت ليُحدّث زره إلى "إضافة صديق"
            await sio.emit('opponent_unfriended', {}, to=target['sid'])
        except Exception:
            await sio.emit('friend_result', {'ok': False, 'msg': 'تعذّر حذف الصديق'}, to=sid)

    @sio.event
    async def block_opponent(sid, data):
        """حظر الخصم. data: { roomCode, token }"""
        room = get_room_state(data.get('roomCode'))
        if not room:
            await sio.emit('block_result', {'ok': False, 'msg': 'الغرفة غير موجودة'}, to=sid)
            return
        target = next((p for p in room['players'] if p['sid'] != sid), None)
        if not target:
            await sio.emit('block_result', {'ok': False, 'msg': 'لا يوجد خصم'}, to=sid)
            return

        from app.sockets.auth_helper import verify_socket_token
        user, db = verify_socket_token(data.get('token'))
        if not user:
            await sio.emit('block_result', {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
            return
        blocker_id = user.id
        db.close()

        target_id = target.get('user_id') or (room.get('user_ids') or {}).get(target['sid'])
        if not target_id:
            await sio.emit('block_result', {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
            return

        from app.services.friends import block_user
        result = block_user(blocker_id, target_id)
        await sio.emit('block_result', result, to=sid)

    @sio.event
    async def unblock_opponent(sid, data):
        """رفع الحظر عن الخصم. data: { roomCode, token }"""
        room = get_room_state(data.get('roomCode'))
        if not room:
            await sio.emit('unblock_result', {'ok': False, 'msg': 'الغرفة غير موجودة'}, to=sid)
            return
        target = next((p for p in room['players'] if p['sid'] != sid), None)
        if not target:
            await sio.emit('unblock_result', {'ok': False, 'msg': 'لا يوجد خصم'}, to=sid)
            return

        from app.sockets.auth_helper import verify_socket_token
        user, db = verify_socket_token(data.get('token'))
        if not user:
            await sio.emit('unblock_result', {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
            return
        my_id = user.id
        db.close()

        target_id = target.get('user_id') or (room.get('user_ids') or {}).get(target['sid'])
        if not target_id:
            await sio.emit('unblock_result', {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
            return

        from app.services.friends import unblock_user
        result = unblock_user(my_id, target_id)
        await sio.emit('unblock_result', result, to=sid)
