import asyncio
import datetime
import json
from app.core.database import SessionLocal, User, GameStat
from app.core.security import get_user_from_token
from app.core.config import settings # 👈 نحتاج الإعدادات لجلب رابط السيرفر
import os

GAME_MODES_ALL = ['huroof', 'bank', 'career', 'whoami', 'whatdo']

def get_level_from_xp(xp: int) -> int:
    """كل مستوى يحتاج 2000 * (level) نقطة XP"""
    level = 0
    xp_needed = 2000
    total = 0
    while xp >= total + xp_needed:
        total += xp_needed
        level += 1
        xp_needed = xp_needed * 2
    return level

def save_match_sync(winner_player: dict, loser_player: dict, game_mode: str, extra: dict=None):
    db = SessionLocal()
    today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    extra = extra or {}
    try:
        for (is_winner, player) in [(True, winner_player), (False, loser_player)]:
            if not player: continue
            token = player.get('token')
            name = player.get('name')
            user = get_user_from_token(db, token)
            
            if not user and name and (name not in ['لاعب', 'مجهول', 'أنت']):
                user = db.query(User).filter(User.player_name.ilike(f'%{name.strip()}%')).first()
            if not user: continue
            
            last_reset = user.last_daily_reset or ''
            if last_reset != today:
                user.daily_games = '{}'
                user.last_daily_reset = today
                user.first_win_claimed = False
                
            daily_games = json.loads(user.daily_games or '{}')
            user.total_matches = (user.total_matches or 0) + 1
            if is_winner: user.wins = (user.wins or 0) + 1
            else: user.losses = (user.losses or 0) + 1
            
            xp_gain = 0
            coins_gain = 0
            gems_gain = 0
            rewards_log = []
            
            if game_mode == 'huroof':
                reason = extra.get('reason', 'normal')
                winner_rounds = extra.get('winner_rounds', 2)
                loser_rounds = extra.get('loser_rounds', 0)
                
                if reason == 'surrender':
                    if is_winner:
                        xp_gain = 150
                        coins_gain = 100
                        rewards_log.append(f'فوز بالانسحاب (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        xp_gain = 0
                        coins_gain = 0
                        rewards_log.append(f'انسحاب من اللعبة (0XP 0🪙)')
                else:
                    if is_winner:
                        if winner_rounds == 2 and loser_rounds == 0:
                            xp_gain = 300
                            coins_gain = 160  
                        elif winner_rounds == 2 and loser_rounds == 1:
                            xp_gain = 250
                            coins_gain = 160
                        else:
                            xp_gain = 250
                            coins_gain = 160
                        rewards_log.append(f'فوز حروف (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        if winner_rounds == 2 and loser_rounds == 0:
                            xp_gain = 40
                            coins_gain = 15
                        elif winner_rounds == 2 and loser_rounds == 1:
                            xp_gain = 50
                            coins_gain = 35  
                        else:
                            xp_gain = 40
                            coins_gain = 15
                        rewards_log.append(f'خسارة حروف (+{xp_gain}XP +{coins_gain}🪙)')
            else:
                if is_winner:
                    xp_gain = 100
                    coins_gain = 50
                    rewards_log.append(f'فوز {game_mode} (+100XP +50🪙)')
                else:
                    xp_gain = 25
                    coins_gain = 10
                    rewards_log.append(f'خسارة {game_mode} (+25XP +10🪙)')
                    
            if is_winner and (not user.first_win_claimed):
                user.first_win_claimed = True
                coins_gain += 100
                gems_gain += 2
                rewards_log.append('🥇 أول فوز اليوم! (+100🪙 +2💎)')
            
            if is_winner:
                last_win = user.last_win_date or ''
                yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                if last_win == today or last_win == yesterday:
                    user.win_streak = (user.win_streak or 0) + 1
                else:
                    user.win_streak = 1
                user.last_win_date = today
                if user.win_streak % 3 == 0:
                    gems_gain += 1
                    rewards_log.append(f'🔥 سلسلة {user.win_streak} انتصار! (+1💎)')
            else:
                user.win_streak = 0
                
            daily_games[game_mode] = True
            user.daily_games = json.dumps(daily_games)
            completed_modes = [m for m in ['huroof', 'what', 'whoami', 'career', 'bank'] if daily_games.get(m)]
            if len(completed_modes) == 5:
                if 'daily_completionist' not in daily_games:
                    daily_games['daily_completionist'] = True
                    user.daily_games = json.dumps(daily_games)
                    gems_gain += 5
                    rewards_log.append('🏅 مكافأة الخماسي اليومية! (+5💎)')
            
            old_level = get_level_from_xp(user.xp or 0)
            user.xp = (user.xp or 0) + xp_gain
            user.coins = (user.coins or 0) + coins_gain
            user.gems = (user.gems or 0) + gems_gain
            new_level = get_level_from_xp(user.xp)
            user.level = new_level
            
            if new_level > old_level:
                user.gems += 3
                user.coins += 200
                rewards_log.append(f'🆙 Level Up! مستوى {new_level} (+3💎 +200🪙)')
                
            stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == game_mode).first()
            if not stat:
                stat = GameStat(user_id=user.id, game_mode=game_mode, matches_played=0, wins=0, losses=0)
                db.add(stat)
            stat.matches_played += 1
            if is_winner: stat.wins += 1
            else: stat.losses += 1
                
            print(f"💾 [{name}] مكافآت: {' | '.join(rewards_log)}")
            
        db.commit()
    except Exception as e:
        print('⚠️ خطأ في حفظ النتيجة:', e)
        db.rollback()
    finally:
        db.close()

def record_match_result(winner_player: dict, loser_player: dict, game_mode: str, extra: dict=None):
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, save_match_sync, winner_player, loser_player, game_mode, extra)
    except Exception as e:
        print("⚠️ خطأ في تشغيل الحفظ الخلفي:", e)

def get_clean_avatar(avatar_val, fallback_name="Player"):
    # 1. إذا لم يكن هناك صورة، نرجع صورة عشوائية
    if not avatar_val or str(avatar_val).strip() == "":
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={fallback_name}"
    
    avatar_str = str(avatar_val).strip()
    
    # 2. الروابط الخارجية (مثل صور جوجل) تبقى كما هي
    if avatar_str.startswith("http") or avatar_str.startswith("data:"):
        return avatar_str
        
    # 3. معالجة الصور المرفوعة (نجلبها من الباك إند ديناميكياً)
    if avatar_str.startswith("/uploads/") or avatar_str.startswith("uploads/"):
        clean_path = avatar_str.replace("//uploads/", "/uploads/").lstrip("/")
        return f"{settings.BACKEND_URL}/{clean_path}"
        
    # 4. الأفاتارات الافتراضية (نجلبها من الفرونت إند ديناميكياً)
    # نستخرج اسم الملف فقط (avatar_1.svg) ونتجاهل أي مسارات نسبية قديمة
    clean_name = avatar_str.split('/')[-1]
    if not clean_name.endswith('.svg') and not clean_name.endswith('.png') and not clean_name.endswith('.jpg'):
        clean_name += '.svg'
        
    return f"{settings.FRONTEND_URL}/assets/avatars/{clean_name}"

def fetch_stats_from_db(token: str, fallback_name: str, fallback_avatar: str):
    default_stats = {
        "name": fallback_name or "لاعب",
        "avatar": get_clean_avatar(fallback_avatar, fallback_name),
        "flag": "../../assets/flags/SA.svg", "rank": "--",
        "huroof": {"wins": 0, "losses": 0, "total": 0}, "global": {"wins": 0, "losses": 0, "total": 0}
    }
    
    db = SessionLocal()
    try:
        user = get_user_from_token(db, token)
        if not user and fallback_name and fallback_name not in ["لاعب", "مجهول", "أنت"]:
            user = db.query(User).filter(User.player_name.ilike(f"%{fallback_name.strip()}%")).first()
            
        if not user: return default_stats
            
        huroof_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == "huroof").first()
        user_xp = user.xp if user.xp is not None else 0
        rank = db.query(User).filter(User.xp > user_xp).count() + 1
        flag_path = f"../../assets/flags/{user.country}.svg" if user.country else default_stats["flag"]
        
        return {
            "name": user.player_name, 
            "avatar": get_clean_avatar(user.avatar, user.player_name), 
            "flag": flag_path, "rank": rank,
            "huroof": {"wins": huroof_stat.wins if huroof_stat else 0, "losses": huroof_stat.losses if huroof_stat else 0, "total": huroof_stat.matches_played if huroof_stat else 0},
            "global": {"wins": user.wins or 0, "losses": user.losses or 0, "total": user.total_matches or 0}
        }
    except Exception as e:
        print(f"🔥 خطأ DB: {e}")
        return default_stats
    finally:
        db.close()

async def get_player_full_stats(token: str, fallback_name: str, fallback_avatar: str):
    return await asyncio.to_thread(fetch_stats_from_db, token, fallback_name, fallback_avatar)