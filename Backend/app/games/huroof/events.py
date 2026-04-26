import asyncio
import html
import random
import json
import time

# ==========================================
# 🔄 الاستيرادات (متوافقة مع الهيكلة الموزعة)
# ==========================================
from app.core.database import SessionLocal, User
# استيراد Question (حسب مسارك، غالباً في database أو models)
try:
    from app.core.database import Question
    from app.models.user import GameStat
except ImportError:
    pass

from app.games.huroof.engine import HuroofGameEngine
from app.services.reward_service import record_match_result
from app.services.telegram_bot import send_secret_to_mobile

from app.sockets.state import (
    get_active_room, delete_active_room, get_connected_player, get_all_online_players,
    add_connected_player, cheat_strikes, redis_db
)
from app.sockets.lobby import return_players_to_lobby

# ============================================================
# 🧠 QUESTIONS CACHE — يُحمَّل مرة واحدة عند تشغيل السيرفر
# جميع الأسئلة في الذاكرة مُجمَّعة حسب الحرف → صفر DB queries أثناء اللعبة
# ============================================================
_QUESTIONS_BY_LETTER: dict = {}

def _build_questions_cache():
    from collections import defaultdict
    db = SessionLocal()
    by_letter = defaultdict(list)
    skipped = 0
    raw_count = 0
    try:
        rows = db.query(Question).filter(
            Question.game_mode.in_(["huroof", "Huroof", "HUROOF", "حروف"])
        ).all()
        raw_count = len(rows)
        print(f"📥 [Cache] تم جلب {raw_count} صف خام من DB")
        for q in rows:
            try:
                extra = json.loads(q.extra_data) if q.extra_data else {}
                letter_raw = extra.get("letter") or (q.correct_answer.strip().lstrip("ال")[0] if q.correct_answer.strip() else "")
                letter = normalize_letter(letter_raw)
                if not letter:
                    skipped += 1
                    continue
                by_letter[letter].append({
                    "id": q.id, "question": q.question_text, "answer": q.correct_answer,
                    "accepted_answers": extra.get("accepted_answers", []),
                    "category": q.category or "",
                })
            except Exception as ex:
                skipped += 1
                if skipped <= 5:
                    print(f"   ⚠️ صف #{getattr(q,'id','?')} فشل: {ex}")
    except Exception as e:
        print(f"⚠️ [Cache] فشل الاستعلام: {e}")
    finally:
        _QUESTIONS_BY_LETTER.update(by_letter)
        total = sum(len(v) for v in by_letter.values())
        print(f"✅ [Cache] حُمّل {total} سؤال لـ {len(by_letter)} حرف (raw={raw_count}, skipped={skipped})")
        db.close()

# متغيرات وضع الجمعات (Party Mode) مؤقتة في الذاكرة
party_session_sid = None
party_session_used_ids = set()

# ✅ Ready tracker في الذاكرة — يستبدل Redis ready_set (أسرع بكثير)
# { room_code: { player_name: sid } }
_room_ready: dict = {}

# ==========================================
# 🛠️ الفلاتر والدوال المساعدة للعبة حروف
# ==========================================
NORMALIZE_LETTER = {
    'ا': 'أ', 'إ': 'أ', 'آ': 'أ',
    'ة': 'ه', 'ى': 'ي', 'ؤ': 'و',
}

def normalize_letter(ch):
    return NORMALIZE_LETTER.get(ch, ch)

_build_questions_cache()

def advance_state(engine, new_stage):
    """تحديث حالة اللعبة وزيادة رقم النسخة — بدون حفظ Redis (المستدعي يحفظ مرة واحدة فقط)"""
    engine.room_data['stage'] = new_stage
    version = engine.room_data.get('state_version', 0) + 1
    engine.room_data['state_version'] = version
    return version

def clean_text_for_match(t):
    """فلتر تنظيف النصوص للتحكيم اللحظي"""
    t = str(t).strip()
    t = t.replace("ال", "", 1) if t.startswith("ال") else t
    return t.replace(" ", "").replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

def check_answer_fast_track(player_ans, correct_ans, accepted_list, required_letter):
    """التحكيم اللحظي (0 ملي ثانية) - 3 فلاتر"""
    p_clean = clean_text_for_match(player_ans)
    req_clean = clean_text_for_match(required_letter)
    
    if not p_clean.startswith(req_clean):
        return False, "wrong_letter"
        
    c_clean = clean_text_for_match(correct_ans)
    if p_clean == c_clean:
        return True, "exact_match"
        
    for acc in accepted_list:
        if p_clean == clean_text_for_match(acc):
            return True, "accepted_match"
            
    return False, "إجابة خاطئة"

def is_bot_or_speedhack(start_time: float, min_human_reaction: float = 0.3) -> bool:
    """تتحقق مما إذا كانت سرعة الاستجابة أسرع من البشر (أقل من 300 مللي ثانية)"""
    if start_time == 0:
        return False 
    elapsed = time.time() - start_time
    return elapsed < min_human_reaction

# ==========================================
# 🎮 تسجيل أحداث السوكيت للعبة حروف
# ==========================================
def register_huroof_events(sio):

    async def huroof_timer_task(room_code, version, seconds, timeout_type):
        await asyncio.sleep(seconds)
        # 🕵️ رادار: هل الغرفة لا تزال موجودة في Redis وبحالة لعب؟
        room_data = await get_active_room(room_code)
        if not room_data or room_data.get('state') != 'playing': return 
            
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data
        
        if gs.get('state_version') != version: return
        
        print(f"⏰ [Timeout] الغرفة {room_code} | النوع: {timeout_type}")
        
        if timeout_type == 'timeout_buzz_r1':
            gs['attempts'] = 2
            new_version = advance_state(engine, 'question')
            gs['buzzed_player'] = None
            await engine._save_state()
            await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, new_version, 30, 'timeout_buzz_r3')

        elif timeout_type == 'timeout_answer_r1':
            new_version = advance_state(engine, 'answer_r2')
            gs['buzzed_player'] = engine.p2 if gs.get('buzzed_player') == engine.p1 else engine.p1
            await engine._save_state()
            await sio.emit('huroof_chance_transfer', {'to_sid': gs['buzzed_player'], 'timer': 20, 'round': 'r2'}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, new_version, 20, 'timeout_answer_r2')
            
        elif timeout_type == 'timeout_answer_r2':
            gs['attempts'] = 2 
            new_version = advance_state(engine, 'question') 
            gs['buzzed_player'] = None
            await engine._save_state()
            await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, new_version, 30, 'timeout_buzz_r3')
            
        elif timeout_type == 'timeout_answer_r3':
            new_version = advance_state(engine, 'answer_r4')
            gs['buzzed_player'] = engine.p2 if gs.get('buzzed_player') == engine.p1 else engine.p1
            await engine._save_state()
            await sio.emit('huroof_chance_transfer', {'to_sid': gs['buzzed_player'], 'timer': 12, 'round': 'r4'}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, new_version, 12, 'timeout_answer_r4')

        elif timeout_type == 'timeout_answer_r4' or timeout_type == 'timeout_buzz_r3':
            advance_state(engine, 'selecting')
            gs['attempts'] = 1 
            gs['turn'] = engine.p2 if gs.get('turn') == engine.p1 else engine.p1
            await engine._save_state()
            await sio.emit('huroof_timeout_info', {'msg': 'انتهى الوقت! نعود لاختيار الحروف.'}, room=room_code)
            await asyncio.sleep(2)
            await sio.emit('huroof_turn_changed', {'turn_sid': gs['turn']}, room=room_code)


    async def trigger_new_question(room_code, room_data=None):
        _tq0 = time.perf_counter()
        if room_data is None:
            room_data = await get_active_room(room_code)
        if not room_data: return
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data

        gs['attempts'] = 1
        active_hex = gs.get('active_hex', {})
        norm_letter = normalize_letter(active_hex.get('letter', ''))

        # ⚡ الكاش أولاً — صفر DB queries أثناء اللعبة
        all_qs_for_letter = _QUESTIONS_BY_LETTER.get(norm_letter, [])

        used_qs = set(gs.get('used_questions', []))

        # أسئلة لم تُستخدم في هذه المباراة بعد
        valid_qs = [q for q in all_qs_for_letter if q['id'] not in used_qs]

        if not valid_qs:
            fallback = {
                "question": f"نفدت الأسئلة الجديدة لحرف ({norm_letter}) لكلاكما. اختاروا حرفاً آخر.",
                "answer": "لا يوجد", "category": "نفدت الأسئلة", "letter": norm_letter, "accepted_answers": []
            }
            await sio.emit('huroof_new_question', {'questionData': fallback, 'round': 'r1', 'timer': 40}, room=room_code)
            return

        chosen = random.choice(valid_qs)

        result = {
            "question":         chosen['question'],
            "answer":           chosen['answer'],
            "accepted_answers": chosen.get('accepted_answers', []),
            "category":         chosen.get('category', ''),
            "letter":           norm_letter,
            "id":               chosen['id'],
        }

        gs.setdefault('used_questions', []).append(result['id'])
        gs.setdefault('used_answers', []).append(result['answer'])
        gs['current_question'] = result

        version = advance_state(engine, 'buzz_r1')
        gs['buzzed_player'] = None
        gs['skip_votes'] = []
        # حفظ واحد فقط لـ Redis بعد كل التعديلات
        await engine._save_state()

        # تحديث seen_question_ids في DB في الخلفية — لا يوقف اللعبة
        async def _update_seen_async():
            def _write():
                db = SessionLocal()
                try:
                    for player in gs.get('players', []):
                        p_name = player.get('name')
                        if not p_name: continue
                        user = db.query(User).filter(User.player_name == p_name).first()
                        if not user: continue
                        try:
                            seen_ids = json.loads(user.seen_question_ids or "[]")
                            if result['id'] not in seen_ids:
                                seen_ids.append(result['id'])
                                user.seen_question_ids = json.dumps(seen_ids)
                        except:
                            user.seen_question_ids = json.dumps([result['id']])
                    db.commit()
                except: pass
                finally: db.close()
            await asyncio.to_thread(_write)

        asyncio.ensure_future(_update_seen_async())
        asyncio.create_task(send_secret_to_mobile(result['question'], result['answer']))

        print(f"⏱️ [trigger_question:{room_code}] TOTAL: {(time.perf_counter()-_tq0)*1000:.1f}ms")
        await sio.emit('huroof_new_question', {'questionData': result, 'round': 'r1', 'timer': 40}, room=room_code)
        sio.start_background_task(huroof_timer_task, room_code, version, 40, 'timeout_buzz_r1')


    async def process_answer_result(room_code, is_correct, player_ans):
        room_data = await get_active_room(room_code)
        if not room_data: return
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data
        
        sid = gs.get('buzzed_player')
        player_color = 'green' if sid == engine.p1 else 'orange'
        
        if is_correct:
            hex_idx = gs['active_hex']['index']
            await sio.emit('huroof_answer_result', {'correct': True, 'answer': player_ans, 'hexIndex': hex_idx, 'color': player_color}, room=room_code)
            
            # تسجيل الخلية والمحرك يفحص الفوز
            is_win = await engine.claim_hex_and_check(hex_idx, player_color)
            
            if is_win:
                await asyncio.sleep(1.5)
                # ✅ جلب room_data طازج بعد claim_hex_and_check لأن المحرك يحدّث الحالة
                room_data = await get_active_room(room_code)
                if not room_data: return
                
                if room_data.get('state') == 'finished':
                    # نهاية المباراة بالكامل
                    winner_p = next((p for p in room_data['players'] if p.get('sid') == engine.p1), None) if player_color == 'green' else next((p for p in room_data['players'] if p.get('sid') == engine.p2), None)
                    loser_p = next((p for p in room_data['players'] if p.get('sid') == engine.p2), None) if player_color == 'green' else next((p for p in room_data['players'] if p.get('sid') == engine.p1), None)
                    
                    try:
                        record_match_result(winner_p, loser_p, room_data.get('mode', 'huroof'), extra={
                            'winner_rounds': room_data.get(f'{player_color}_wins', 0),
                            'loser_rounds': room_data.get(f'{"orange" if player_color == "green" else "green"}_wins', 0)
                        })
                    except: pass

                    await sio.emit('huroof_match_over', {
                        'winner': player_color, 'points': room_data.get('points', {}), 'reason': 'normal'
                    }, room=room_code)

                    await asyncio.sleep(2)
                    await return_players_to_lobby(sio, {'players': room_data['players'], 'game_mode': room_data.get('mode', 'huroof')})
                    await delete_active_room(room_code)
                    print(f"🗑️ تم حذف الغرفة {room_code} بعد انتهاء المباراة.")
                else:
                    # نهاية جولة فقط وبدء جولة جديدة
                    await sio.emit('huroof_round_over', {
                        'winner': player_color, 'points': room_data.get('points', {}), 'next_round': room_data.get('round_number')
                    }, room=room_code)
                    
                    await asyncio.sleep(3)
                    await sio.emit('huroof_board_init', {'board': room_data['board']}, room=room_code)
                    await sio.emit('huroof_new_round_started', {'turn': room_data['turn']}, room=room_code)
            else:
                # لم يفز بعد — نعود لاختيار الحرف
                await asyncio.sleep(1.5)
                # ✅ جلب حالة طازجة بعد claim_hex
                room_data = await get_active_room(room_code)
                if not room_data: return
                engine2 = HuroofGameEngine(room_code, room_data)
                gs2 = engine2.room_data
                # تحويل الدور للخصم
                gs2['stage'] = 'selecting'
                gs2['attempts'] = 1
                gs2['turn'] = engine2.p2 if gs2.get('turn') == engine2.p1 else engine2.p1
                await engine2._save_state()
                await sio.emit('huroof_turn_changed', {'turn_sid': gs2['turn']}, room=room_code)
        else:
            hex_idx = gs['active_hex']['index']
            await sio.emit('huroof_answer_result', {'correct': False, 'answer': player_ans, 'hexIndex': hex_idx}, room=room_code)
            await asyncio.sleep(1.5)
            
            # جلب حالة طازجة
            room_data = await get_active_room(room_code)
            if not room_data: return
            engine = HuroofGameEngine(room_code, room_data)
            gs = engine.room_data

            stage = gs.get('stage')
            if stage == 'answer_r1':
                version = advance_state(engine, 'answer_r2')
                gs['buzzed_player'] = engine.p2 if gs.get('buzzed_player') == engine.p1 else engine.p1
                await engine._save_state()
                await sio.emit('huroof_chance_transfer', {'to_sid': gs['buzzed_player'], 'timer': 20, 'round': 'r2'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
                
            elif stage == 'answer_r2':
                gs['attempts'] = 2
                version = advance_state(engine, 'question') 
                gs['buzzed_player'] = None
                await engine._save_state()
                await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code) 
                sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')
                
            elif stage == 'answer_r3':
                version = advance_state(engine, 'answer_r4')
                gs['buzzed_player'] = engine.p2 if gs.get('buzzed_player') == engine.p1 else engine.p1
                await engine._save_state()
                await sio.emit('huroof_chance_transfer', {'to_sid': gs['buzzed_player'], 'timer': 12, 'round': 'r4'}, room=room_code)
                sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')
                
            elif stage == 'answer_r4':
                advance_state(engine, 'selecting')
                gs['attempts'] = 1
                gs['turn'] = engine.p2 if gs.get('turn') == engine.p1 else engine.p1
                await engine._save_state()
                await sio.emit('huroof_timeout_info', {'msg': 'كلاكما أخطأ! نعود للاختيار.'}, room=room_code)
                await asyncio.sleep(2)
                await sio.emit('huroof_turn_changed', {'turn_sid': gs['turn']}, room=room_code)


    # --- أحداث اللاعبين الأساسية ---

    @sio.event
    async def huroof_player_ready(sid, data):
        _t0 = time.perf_counter()
        room_code = data.get('roomId') or data.get('roomCode')
        player_name = data.get('playerName') or data.get('name')
        frontend_avatar = data.get('avatar')
        fresh_avatar = frontend_avatar if frontend_avatar and str(frontend_avatar).strip() != '' else "assets/avatars/avatar_1.svg"

        from app.sockets.state import add_connected_player, get_all_online_players
        if not room_code or not player_name: return

        # تسجيل الجاهزية في الذاكرة
        if room_code not in _room_ready:
            _room_ready[room_code] = {}
        _room_ready[room_code][player_name] = (sid, fresh_avatar)
        ready_count = len(_room_ready[room_code])

        # تحديث اللوبي في الخلفية
        async def _update_lobby_async():
            await add_connected_player(sid, {
                'name': player_name, 'avatar': fresh_avatar,
                'location': 'playing_huroof', 'status': 'في مباراة'
            })
            await sio.emit('update_online_players', await get_all_online_players())
        asyncio.ensure_future(_update_lobby_async())

        # 🚀 جلب الغرفة فوراً (لا ننتظر اللاعب الثاني)
        room_data = await get_active_room(room_code)
        if not room_data: return

        # تحديث SID وصورة هذا اللاعب
        for p in room_data['players']:
            if p.get('name') == player_name:
                p['sid'] = sid
                p['avatar'] = fresh_avatar

        engine = HuroofGameEngine(room_code, room_data)
        colors = ['green', 'orange']

        # بناء اللوحة لو ما بُنيت (اللاعب الأول)
        board_just_built = False
        if 'board' not in room_data:
            engine._reset_board_logic()
            room_data.update({
                'green_wins': 0, 'orange_wins': 0, 'round_number': 1,
                'points': {'green': 0, 'orange': 0}, 'used_questions': [],
                'used_answers': [], 'state_version': 0,
            })
            board_just_built = True

        players_list = room_data['players']
        basic_players = [
            {'name': p.get('name'), 'avatar': p.get('avatar', ''), 'sid': p.get('sid', ''), 'color': colors[i]}
            for i, p in enumerate(players_list)
        ]

        # ترتيب اللاعبين بحيث "أنا" دائماً أولاً
        me_idx = next((i for i, p in enumerate(players_list) if p.get('name') == player_name), 0)
        op_idx = 1 - me_idx
        me_data = {
            'sid': sid, 'name': players_list[me_idx].get('name'),
            'avatar': players_list[me_idx].get('avatar', ''),
            'color': colors[me_idx], 'stats': None
        }
        op_data = {
            'sid': players_list[op_idx].get('sid', ''),
            'name': players_list[op_idx].get('name'),
            'avatar': players_list[op_idx].get('avatar', ''),
            'color': colors[op_idx], 'stats': None
        }

        # 🚀 إرسال فوري لهذا اللاعب: room_joined + board (لا ينتظر الخصم)
        _ti = time.perf_counter()
        await asyncio.gather(
            sio.enter_room(sid, room_code),
            engine._save_state() if board_just_built else asyncio.sleep(0),
        )
        await asyncio.gather(
            sio.emit('room_joined', {'players': [me_data, op_data]}, to=sid),
            sio.emit('huroof_board_init', {'board': room_data['board'], 'players': basic_players}, to=sid),
        )
        print(f"⏱️ [ready:{player_name}] إرسال فوري للاعب: {(time.perf_counter()-_ti)*1000:.1f}ms")

        # إحصائيات DB لهذا اللاعب في الخلفية
        asyncio.ensure_future(_send_single_player_stats(sid, player_name, fresh_avatar, players_list, colors, me_idx, op_idx))

        # 🎯 لو وصل اللاعب الثاني الآن، ابدأ الجولة فعلياً للاعبين الاثنين
        if ready_count >= 2:
            _room_ready.pop(room_code, None)
            # ضمان أن الدور صحيح
            if room_data.get('turn') not in {engine.p1, engine.p2}:
                room_data['turn'] = engine.p1
                await engine._save_state()
            await sio.emit('huroof_new_round_started', {'turn': room_data['turn']}, room=room_code)
            print(f"⏱️ [ready:{player_name}] انطلاق المباراة، TOTAL: {(time.perf_counter()-_t0)*1000:.1f}ms")
        else:
            # رسالة انتظار للاعب الأول
            await sio.emit('huroof_waiting_opponent', {'msg': 'في انتظار دخول الخصم...'}, to=sid)


    # دالة مساعدة جديدة (ضعها قبل huroof_player_ready مباشرة)
    async def _send_single_player_stats(sid, player_name, fresh_avatar, players_list, colors, me_idx, op_idx):
        def get_player_full_stats(p_name: str, fallback_avatar: str) -> dict:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.player_name == p_name).first()
                if not user: return {}
                huroof_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == 'huroof').first()
                all_stats = db.query(GameStat).filter(GameStat.user_id == user.id).all()
                return {
                    'name': user.player_name,
                    'avatar': fallback_avatar or user.avatar or '',
                    'flag': f'../assets/flags/{user.country or "SA"}.svg',
                    'rank': f'المستوى {user.level}',
                    'huroof': {
                        'wins': huroof_stat.wins if huroof_stat else 0,
                        'losses': huroof_stat.losses if huroof_stat else 0,
                        'total': huroof_stat.matches_played if huroof_stat else 0,
                    },
                    'global': {
                        'wins': sum(s.wins for s in all_stats),
                        'losses': sum(s.losses for s in all_stats),
                        'total': sum(s.matches_played for s in all_stats),
                    },
                }
            except Exception:
                return {}
            finally:
                db.close()

        me_stats, op_stats = await asyncio.gather(
            asyncio.to_thread(get_player_full_stats, players_list[me_idx].get('name', ''), fresh_avatar),
            asyncio.to_thread(get_player_full_stats, players_list[op_idx].get('name', ''), players_list[op_idx].get('avatar', '')),
        )
        await sio.emit('update_players_stats', [
            {'sid': sid, 'name': players_list[me_idx].get('name'), 'color': colors[me_idx], 'stats': me_stats},
            {'sid': players_list[op_idx].get('sid', ''), 'name': players_list[op_idx].get('name'), 'color': colors[op_idx], 'stats': op_stats},
        ], to=sid)

        async def _send_stats_later():
            all_stats = await asyncio.gather(
                *[asyncio.to_thread(get_player_full_stats, p.get('name', ''), p.get('avatar', ''))
                  for p in players_list]
            )
            stat_tasks = []
            for i, p in enumerate(players_list):
                if p.get('sid'):
                    stat_tasks.append(
                        sio.emit('update_players_stats', [
                            {'sid': p.get('sid'), 'name': p.get('name'), 'color': colors[i], 'stats': all_stats[i]},
                            {'sid': players_list[1-i].get('sid', ''), 'name': players_list[1-i].get('name'), 'color': colors[1-i], 'stats': all_stats[1-i]},
                        ], to=p.get('sid'))
                    )
            if stat_tasks:
                await asyncio.gather(*stat_tasks)

        asyncio.ensure_future(_send_stats_later())

    @sio.event
    async def huroof_select_hex(sid, data):
        room_code = data.get('roomCode')
        hex_index = data.get('hexIndex')
        
        room_data = await get_active_room(room_code)
        if not room_data: return
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data
        
        if gs.get('stage') != 'selecting' or gs.get('turn') != sid:
            return 
        _ts = time.perf_counter()
            
        gs['active_hex'] = gs['board'][hex_index]
        # ✅ أولاً: حفظ الحالة + إرسال hex_locked بالتوازي
        await asyncio.gather(
            engine._save_state(),
            sio.emit('huroof_hex_locked', {'hexIndex': hex_index, 'letter': gs['active_hex']['letter']}, room=room_code)
        )
        print(f"⏱️ [select_hex] save+emit: {(time.perf_counter()-_ts)*1000:.1f}ms")
        # ✅ جلب room_data طازج من Redis لتجنب أي تعارض، ثم trigger السؤال
        fresh_room_data = await get_active_room(room_code)
        await trigger_new_question(room_code, fresh_room_data)

    @sio.event
    async def huroof_buzz(sid, data):
        room_code = data.get('roomCode')
        room_data = await get_active_room(room_code)
        if not room_data: return
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data
        
        allowed_stages = ['question', 'buzz_r1', 'buzz_r3']
        if gs.get('stage') not in allowed_stages: return
        
        gs['buzzed_player'] = sid
        gs['answer_start_time'] = time.time()
        if 'attempts' not in gs: gs['attempts'] = 1

        if gs['attempts'] == 1:
            current_time = 15
            version = advance_state(engine, 'answer_r1')
            timeout_type = 'timeout_answer_r1'
        else:
            current_time = 12
            version = advance_state(engine, 'answer_r3')
            timeout_type = 'timeout_answer_r3'
        
        print(f"🔔 {sid} ضغط الجرس - محاولة رقم: {gs['attempts']} - وقت: {current_time}ث")
        
        await sio.emit('huroof_buzzed', {'sid': sid, 'time': current_time}, room=room_code)
        sio.start_background_task(huroof_timer_task, room_code, version, current_time, timeout_type)

    @sio.event
    async def huroof_submit_answer(sid, data):
        room_code = data.get('roomCode')
        player_ans = html.escape(str(data.get('answer', '')).strip())
        
        room_data = await get_active_room(room_code)
        if not room_data: return
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data

        # 🛡️ الحماية 1: التحقق من الحالة
        if gs.get('stage') not in ['answer_r1', 'answer_r2', 'answer_r3', 'answer_r4']: return 
        if sid != gs.get('buzzed_player'): return 

        # 🛡️ الحماية 2: مكافحة البوتات (سرعة الإجابة)
        if is_bot_or_speedhack(gs.get('answer_start_time', 0), min_human_reaction=0.4):
            player = await get_connected_player(sid)
            player_name = player.get('name', 'مجهول') if player else 'مجهول'
            
            current_strikes = cheat_strikes.get(player_name, 0) + 1
            cheat_strikes[player_name] = current_strikes
            
            if current_strikes == 1:
                print(f"⚠️ [إنذار أول] سرعة غير طبيعية من اللاعب {player_name}")
                await sio.emit("cheat_warning", {"message": "تحذير 🚨: تم اكتشاف سرعة إجابة غير بشرية. إذا تكرر ذلك سيتم حظرك!"}, to=sid)
                return 
            else:
                print(f"🚫 [حظر نهائي] تكرار الغش من اللاعب {player_name}")
                db = SessionLocal()
                db_user = db.query(User).filter(User.player_name == player_name).first()
                if db_user:
                    db_user.is_banned = True
                    db.commit()
                db.close()
                await sio.emit("force_logout", {"message": "تم حظر حسابك نهائياً بسبب استخدام برامج مساعدة (Bots)."}, to=sid)
                await sio.disconnect(sid)
                return

        if not player_ans: return 
        
        current_question = gs.get('current_question', {})
        req_letter = current_question.get('letter', '')
        
        p_clean = clean_text_for_match(player_ans)
        req_clean = clean_text_for_match(req_letter)
        
        if not p_clean.startswith(req_clean):
            print(f"⚠️ [Anti-Cheat] محاولة تجاوز حرف {req_clean} من {sid}")
            return
        
        # ✅ التحكيم الذكي
        correct_ans = current_question.get('answer', '')
        accepted_list = current_question.get('accepted_answers', [])
        
        is_correct, reason = check_answer_fast_track(player_ans, correct_ans, accepted_list, req_letter)
        await process_answer_result(room_code, is_correct, player_ans)

    @sio.event
    async def huroof_vote_skip(sid, data):
        room_code = data.get('roomCode')
        room_data = await get_active_room(room_code)
        if not room_data or room_data.get('state') != 'playing': return
        engine = HuroofGameEngine(room_code, room_data)
        gs = engine.room_data
        
        if gs.get('stage') in ['buzz_r1', 'buzz_r3', 'question']:
            skip_votes = gs.get('skip_votes', [])
            if sid not in skip_votes:
                skip_votes.append(sid)
                gs['skip_votes'] = skip_votes
                await engine._save_state()
                
                await sio.emit('huroof_skip_voted', {'sid': sid}, room=room_code)
                
                if len(skip_votes) >= 2:
                    print(f"🔄 [Skipping] اتفاق على تغيير السؤال في الغرفة {room_code}")
                    await sio.emit('huroof_timeout_info', {'msg': 'تم الاتفاق! جاري جلب سؤال جديد...'}, room=room_code)
                    advance_state(engine, 'selecting') # لزيادة النسخة ووقف المؤقتات
                    await trigger_new_question(room_code, room_data)

    @sio.event
    async def huroof_surrender(sid, data):
        """نظام الانسحاب المحدث"""
        room_code = data.get('roomCode') or data.get('roomId')
        room_data = await get_active_room(room_code)
        
        if room_data:
            players = room_data.get('players', [])
            if not players: return
            
            # تحديد الفائز والخاسر بناءً على الـ SID
            if len(players) > 0 and players[0].get('sid') == sid:
                winner_color = 'orange'
                loser_player = players[0]
                winner_player = players[1] if len(players) > 1 else None
            else:
                winner_color = 'green'
                loser_player = next((p for p in players if p.get('sid') == sid), None)
                winner_player = next((p for p in players if p.get('sid') != sid), None)
            
            try:
                record_match_result(winner_player, loser_player, room_data.get('mode', 'huroof'), extra={'reason': 'surrender'})
            except: pass

            print(f"🏳️ انسحاب! الفائز هو {winner_color}")

            # 🚀 إرسال حدث 'huroof_match_over' لأن الفرونت إند ينتظر هذا الحدث ليعرض النتيجة!
            await sio.emit('huroof_match_over', {
                'winner': winner_color, 
                'points': room_data.get('points', {'green':0, 'orange':0}), 
                'reason': 'surrender'
            }, room=room_code)
            
            await asyncio.sleep(2)
            await delete_active_room(room_code)

    # ==========================================
    # 🎉 وضع الجمعات (Party Mode)
    # ==========================================

    @sio.event
    async def join_party_mode(sid, data):
        global party_session_sid, party_session_used_ids
        game_mode = data.get('gameMode', 'huroof')
        player_name = data.get('name', 'لاعب')
        avatar = data.get('avatar', 'https://api.dicebear.com/7.x/bottts/svg?seed=Hero')
        
        player_data = {'name': player_name, 'avatar': avatar, 'location': f"party_{game_mode}"}
        await add_connected_player(sid, player_data)
        
        print(f"[*] {player_name} دخل وضع الجمعات في: {game_mode}")

        if party_session_sid is None:
            party_session_sid = sid
            party_session_used_ids = set()
            print(f"🎉 [Party] جلسة جديدة بدأت - المضيف: {player_name} ({sid})")
        
        online_players = await get_all_online_players()
        await sio.emit('update_online_players', online_players)

    @sio.event
    async def request_ai_question(sid, data):
        global party_session_used_ids
        letter = data.get('letter', 'أ').strip()
        requested_category = data.get('category', 'عام')
        norm_letter = normalize_letter(letter)

        db = SessionLocal()
        try:
            query = db.query(Question).filter(Question.game_mode == "huroof")
            if requested_category != 'عام':
                query = query.filter(Question.category == requested_category)

            all_qs = query.all()

            valid = []
            for q in all_qs:
                if q.id in party_session_used_ids: continue
                try:
                    ans = q.correct_answer.strip()
                    if ans.startswith("ال"): ans = ans[2:]
                    extra = json.loads(q.extra_data) if q.extra_data else {}
                    if normalize_letter(extra.get("letter", "")) == norm_letter or normalize_letter(ans[0]) == norm_letter:
                        valid.append(q)
                except: pass

            if valid:
                chosen = random.choice(valid)
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
                print(f"⚠️ [Party] نفدت أسئلة حرف '{norm_letter}' بتصنيف '{requested_category}'.")
                fallback = {
                    "question": f"عذراً، نفدت أسئلة حرف ({norm_letter}) في هذا التصنيف. جرب تصنيفاً آخر.",
                    "answer": "لا يوجد", "category": "نفدت الأسئلة", "letter": norm_letter, "accepted_answers": []
                }
                await sio.emit('receive_ai_question', fallback, to=sid)
        finally:
            db.close()