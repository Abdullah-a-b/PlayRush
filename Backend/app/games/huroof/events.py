import asyncio
import html
import random
import json

# ==========================================
# 🔄 الاستيرادات من الهيكلة الجديدة (تأكد من مطابقتها لمساراتك)
# ==========================================
from app.core.database import SessionLocal, Question, User
from app.games.core_manager import get_room_state, rooms
from app.services.reward_service import record_match_result
from app.services.telegram_bot import send_secret_to_mobile

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

    async def huroof_timer_task(room_code, version, seconds, timeout_type):
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
                # 4️⃣ انتهت كل الفرص أو لم يضغط أحد في الفرصة الثانية -> تغيير السؤال
                advance_state(gs, 'selecting')
                gs.attempts = 1 
                gs.turn = gs.p2 if gs.turn == gs.p1 else gs.p1
                await sio.emit('huroof_timeout_info', {'msg': 'انتهى الوقت! نعود لاختيار الحروف.'}, room=room_code)
                await asyncio.sleep(2)
                await sio.emit('huroof_turn_changed', {'turn_sid': gs.turn}, room=room_code)

    async def trigger_new_question(room_code):
        print(f"\n🔄 [السيرفر] طلب سؤال جديد للغرفة: {room_code}")
        room = get_room_state(room_code)
        if not room or not room.get('game_state'): return
        gs = room['game_state']
        gs.attempts = 1

        norm_letter = normalize_letter(gs.active_hex['letter'])
        print(f"🎯 [السيرفر] تم الضغط على الحرف: {norm_letter}")

        db = SessionLocal()
        combined_seen = set()  
        player_db_ids = {}     

        try:
            for player in room.get('players', []):
                p_sid = player.get('sid')
                if not p_sid:
                    continue
                token = connected_players.get(p_sid, {}).get('token')
                user = None
                if token:
                    user = db.query(User).filter(User.session_token == token).first() # تأكد من اسم الحقل أو استخدم auth_provider logic
                if user:
                    try:
                        seen_ids = json.loads(user.seen_question_ids or "[]")
                        combined_seen.update(seen_ids)
                        player_db_ids[p_sid] = user.id
                        print(f"📖 [{player.get('name')}] سجله: {len(seen_ids)} سؤال مشاهَد")
                    except Exception:
                        pass

            valid_qs = []
            query = db.query(Question).filter(Question.game_mode == "huroof")
            for q in query.all():
                if hasattr(gs, 'used_questions') and q.id in gs.used_questions:
                    continue
                if q.id in combined_seen:
                    continue
                try:
                    ans = q.correct_answer.strip()
                    if ans.startswith("ال"):
                        ans = ans[2:]
                    extra = json.loads(q.extra_data) if q.extra_data else {}
                    letter_from_extra = normalize_letter(extra.get("letter", ""))
                    letter_from_ans = normalize_letter(ans[0]) if ans else ""
                    if letter_from_extra == norm_letter or letter_from_ans == norm_letter:
                        valid_qs.append(q)
                except (json.JSONDecodeError, AttributeError, IndexError, TypeError):
                    pass

            print(f"📊 [السيرفر] أسئلة جديدة لكليهما لهذا الحرف: {len(valid_qs)}")

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

            chosen = random.choice(valid_qs)

            if hasattr(gs, 'used_questions'):
                gs.used_questions.append(chosen.id)
                gs.used_answers.append(chosen.correct_answer)

            for p_sid, user_id in player_db_ids.items():
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    try:
                        seen_ids = json.loads(user.seen_question_ids or "[]")
                        if chosen.id not in seen_ids:
                            seen_ids.append(chosen.id)
                            user.seen_question_ids = json.dumps(seen_ids)
                    except Exception:
                        user.seen_question_ids = json.dumps([chosen.id])
            db.commit()
            print(f"💾 [سجل] تم حفظ ID={chosen.id} في سجل اللاعبَين")

            extra = json.loads(chosen.extra_data) if chosen.extra_data else {}
            gs.current_question = {
                "question": chosen.question_text,
                "answer": chosen.correct_answer,
                "accepted_answers": extra.get("accepted_answers", []),
                "category": chosen.category,
                "letter": norm_letter
            }

            version = advance_state(gs, 'buzz_r1')
            gs.buzzed_player = None
            gs.skip_votes.clear()

            # 🛡️ ANTI-CHEAT: track when question was shown for reaction time validation
            import time as _time
            gs.question_shown_at = _time.time()

            asyncio.create_task(send_secret_to_mobile(gs.current_question['question'], gs.current_question['answer']))

            print(f"✅ [السيرفر] إرسال السؤال للمتصفح: {gs.current_question['question']}")
            await sio.emit('huroof_new_question', {
                'questionData': gs.current_question,
                'round': 'r1',
                'timer': 40
            }, room=room_code)

            sio.start_background_task(huroof_timer_task, room_code, version, 40, 'timeout_buzz_r1')

        finally:
            db.close()

    async def process_answer_result(room_code, is_correct, player_ans):
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
                        
                        record_match_result(winner_player, loser_player, room.get('game_mode', 'huroof'), extra={
                            'winner_rounds': gs.points[player_color],
                            'loser_rounds':  gs.points[loser_color]
                        })

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
                await sio.emit('huroof_turn_changed', {'turn_sid': sid}, room=room_code)
                
        else:
            await sio.emit('huroof_answer_result', {'correct': False, 'answer': player_ans, 'hexIndex': gs.active_hex['index']}, room=room_code)
            await asyncio.sleep(1.5)
            
            if gs.stage == 'answer_r1':
                version = advance_state(gs, 'answer_r2')
                gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
                await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 20, 'round': 'r2'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
                
            elif gs.stage == 'answer_r2':
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
                advance_state(gs, 'selecting')
                gs.attempts = 1
                gs.turn = gs.p2 if gs.turn == gs.p1 else gs.p1
                await sio.emit('huroof_timeout_info', {'msg': 'كلاكما أخطأ! نعود للاختيار.'}, room=room_code)
                await asyncio.sleep(2)
                await sio.emit('huroof_turn_changed', {'turn_sid': gs.turn}, room=room_code)

    @sio.event
    async def huroof_select_hex(sid, data):
        room_code = data.get('roomCode')
        hex_index = data.get('hexIndex')
        
        room = get_room_state(room_code)
        if not room: return
        gs = room['game_state']
        
        if gs.stage != 'selecting' or gs.turn != sid:
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

        print(f"🔔 {sid} ضغط الجرس - محاولة رقم: {gs.attempts} - وقت: {current_time}ث")

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

        correct_ans = gs.current_question['answer']
        accepted_list = gs.current_question['accepted_answers']
        req_letter = gs.current_question['letter']

        is_correct, reason = check_answer_fast_track(player_ans, correct_ans, accepted_list, req_letter)

        await process_answer_result(room_code, is_correct, player_ans)

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
                print(f"🔄 [Skipping] اتفاق على تغيير السؤال في الغرفة {room_code}")
                await sio.emit('huroof_timeout_info', {'msg': 'تم الاتفاق! جاري جلب سؤال جديد...'}, room=room_code)
                gs.state_version += 1 
                await trigger_new_question(room_code)

    @sio.event
    async def huroof_surrender(sid, data):
        room_code = data.get('roomCode')
        room = get_room_state(room_code)
        
        if room:
            winner_color = 'orange' if room['players'][0]['sid'] == sid else 'green'
            
            loser_player = next((p for p in room['players'] if p['sid'] == sid), None)
            winner_player = next((p for p in room['players'] if p['sid'] != sid), None)
            record_match_result(winner_player, loser_player, room.get('game_mode', 'huroof'), extra={'reason': 'surrender'})

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
        print(f"[*] {player_name} دخل وضع الجمعات في: {game_mode}")

        if state.party_session_sid is None:
            state.party_session_sid = sid
            state.party_session_used_ids = set()
            print(f"🎉 [Party] جلسة جديدة بدأت - المضيف: {player_name} ({sid})")
        
        await sio.emit('update_online_players', list(connected_players.values()))

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
                print(f"⚡ [Party] سؤال جديد ID={chosen.id} | إجمالي المستخدمة: {len(party_session_used_ids)}")
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