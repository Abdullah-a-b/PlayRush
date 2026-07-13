import asyncio
import datetime
import json
from app.core.database import SessionLocal, User, GameStat
from app.core.security import get_user_from_token
from app.core.config import settings # 👈 نحتاج الإعدادات لجلب رابط السيرفر
import os

GAME_MODES_ALL = ['huroof', 'bank', 'career', 'whoami', 'whatdo']

def get_level_from_xp(xp: int) -> int:
    """منحنى تلفيل متدرّج خطّي (يبدأ من المستوى 0).
    XP المطلوب L→L+1 = 120 + (L * 80). متدرّج وعادل."""
    if xp is None or xp < 0:
        return 0
    level = 0
    total = 0
    xp_needed = 120
    while xp >= total + xp_needed:
        total += xp_needed
        level += 1
        xp_needed = 120 + (level * 80)
    return level


def xp_for_next_level(xp: int) -> dict:
    """تفاصيل تقدّم المستوى (لشريط XP)."""
    if xp is None or xp < 0:
        xp = 0
    level = 0
    total = 0
    xp_needed = 120
    while xp >= total + xp_needed:
        total += xp_needed
        level += 1
        xp_needed = 120 + (level * 80)
    return {
        'level': level,
        'current_in_level': xp - total,
        'needed_for_next': xp_needed,
        'total_xp': xp,
    }

def save_match_sync(winner_player: dict, loser_player: dict, game_mode: str, extra: dict=None):
    extra = extra or {}
    # 🤝 مباراة ودية (دعوة صديق): لا تُحتسب إطلاقاً — لا تصنيف، لا مستوى،
    #    لا جواهر، لا كوينز، ولا حتى إحصائيات فوز/خسارة. مجرد لعب للمتعة.
    if extra.get('friendly'):
        print("🤝 [match] مباراة ودية بين صديقين — لا مكافآت ولا إحصائيات")
        return

    db = SessionLocal()
    today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    try:
        for (is_winner, player) in [(True, winner_player), (False, loser_player)]:
            if not player: continue
            token = player.get('token')
            name = player.get('name')
            user = get_user_from_token(db, token)

            # ✅ إصلاح: نستخدم exact match (==) بدل ilike fuzzy match
            if not user and name and (name not in ['لاعب', 'مجهول', 'أنت']):
                user = db.query(User).filter(User.player_name == name.strip()).first()
            if not user:
                print(f"⚠️ [reward] لم يُعثر على المستخدم: token={token[:10] if token else 'None'}... name={name}")
                continue

            # ✅ Race condition fix: قفل الصف لمنع double rewards عند reconnect سريع
            # SELECT ... FOR UPDATE — يمنع worker آخر من تعديل نفس الصف بالتزامن
            user = db.query(User).filter(User.id == user.id).with_for_update().first()
            if not user:
                continue
            
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
            reason = extra.get('reason', 'normal')
            
            if game_mode == 'huroof':
                winner_rounds = extra.get('winner_rounds', 2)
                loser_rounds = extra.get('loser_rounds', 0)
                
                if reason == 'surrender':
                    if is_winner:
                        # 🏆 الفائز بالانسحاب يحصل على نفس مكافأة فوز 2-0 (لا فرق)
                        xp_gain = 40
                        coins_gain = 60
                        rewards_log.append(f'فوز بالانسحاب (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        # ❌ المنسحب لا يحصل على شيء (عقوبة)
                        xp_gain = 0
                        coins_gain = 0
                        rewards_log.append('انسحاب من اللعبة (0XP 0🪙)')
                else:
                    # 🎯 نظام المكافآت الجديد (حروف): الأداء + المشاركة الثابتة (20🪙+15XP)
                    if is_winner:
                        if winner_rounds == 2 and loser_rounds == 0:
                            xp_gain = 40
                            coins_gain = 60
                        else:  # فوز 2-1
                            xp_gain = 30
                            coins_gain = 50
                        rewards_log.append(f'فوز خلية الحروف (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        if winner_rounds == 2 and loser_rounds == 1:  # خسارة 2-1
                            xp_gain = 25
                            coins_gain = 40
                        else:  # خسارة 2-0
                            xp_gain = 15
                            coins_gain = 20
                        rewards_log.append(f'خسارة خلية الحروف (+{xp_gain}XP +{coins_gain}🪙)')
            else:
                # 🎯 باقي المسابقات: فوز=50🪙/35XP، خسارة=20🪙/15XP
                # الانسحاب: الفائز يأخذ مكافأة الفوز كاملة، المنسحب صفر
                if reason == 'surrender':
                    if is_winner:
                        xp_gain = 35
                        coins_gain = 50
                        rewards_log.append(f'فوز بالانسحاب (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        xp_gain = 0
                        coins_gain = 0
                        rewards_log.append('انسحاب من اللعبة (0XP 0🪙)')
                elif is_winner:
                    xp_gain = 35
                    coins_gain = 50
                    rewards_log.append(f'فوز {game_mode} (+{xp_gain}XP +{coins_gain}🪙)')
                else:
                    xp_gain = 15
                    coins_gain = 20
                    rewards_log.append(f'خسارة {game_mode} (+{xp_gain}XP +{coins_gain}🪙)')
                    
            if is_winner and (not user.first_win_claimed):
                user.first_win_claimed = True
                coins_gain += 100
                rewards_log.append('🥇 أول فوز اليوم! (+100🪙)')
            
            if is_winner:
                last_win = user.last_win_date or ''
                yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                if last_win == today or last_win == yesterday:
                    user.win_streak = (user.win_streak or 0) + 1
                else:
                    user.win_streak = 1
                user.last_win_date = today
                # 💎 إزالة جوهرة كل 3 انتصارات — الجواهر ستأتي من نظام المهام/التصنيف مستقبلاً
            else:
                user.win_streak = 0
                
            daily_games[game_mode] = True
            user.daily_games = json.dumps(daily_games)
            completed_modes = [m for m in ['huroof', 'what', 'whoami', 'career', 'bank'] if daily_games.get(m)]
            if len(completed_modes) == 5:
                if 'daily_completionist' not in daily_games:
                    daily_games['daily_completionist'] = True
                    user.daily_games = json.dumps(daily_games)
                    # 💎 مكافأة الخماسي اليومية ستُنقل لنظام المهام اليومية مستقبلاً
                    coins_gain += 200
                    rewards_log.append('🏅 مكافأة الخماسي اليومية! (+200🪙)')
            
            # 🛡️ تطبيق معامل مكافحة التواطؤ (يقلّل الجائزة لو المواجهة متكررة)
            collusion_mult = extra.get('collusion_multiplier', 1.0)
            if collusion_mult < 1.0:
                xp_gain = int(xp_gain * collusion_mult)
                coins_gain = int(coins_gain * collusion_mult)
                gems_gain = int(gems_gain * collusion_mult)
                if collusion_mult == 0.0:
                    rewards_log.append('⚠️ لا جوائز: مواجهات متكررة مع نفس اللاعب')
                else:
                    rewards_log.append(f'⚠️ جائزة مخفّضة ({int(collusion_mult*100)}%): مواجهات متكررة')

            old_level = get_level_from_xp(user.xp or 0)
            user.xp = (user.xp or 0) + xp_gain
            user.coins = (user.coins or 0) + coins_gain
            user.gems = (user.gems or 0) + gems_gain
            new_level = get_level_from_xp(user.xp)
            user.level = new_level
            
            if new_level > old_level:
                user.coins += 200
                rewards_log.append(f'🆙 Level Up! مستوى {new_level} (+200🪙)')
                
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
    """يسجّل نتيجة المباراة. يعمل في كل السياقات:
    - داخل thread (asyncio.to_thread): لا event loop → نحفظ مباشرة.
    - داخل async loop: نجدول الحفظ في executor (لا نحجب الloop).
    الجذر السابق: get_running_loop() كان يفشل داخل to_thread (لا loop)
    فيُلتقط الاستثناء ولا تُحفظ المباراة أبداً → البروفايل يعرض 0.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        # نحن داخل async loop → نجدول بلا حجب
        loop.run_in_executor(None, save_match_sync, winner_player, loser_player, game_mode, extra)
    else:
        # نحن داخل thread (to_thread) أو سياق متزامن → نحفظ مباشرة
        try:
            save_match_sync(winner_player, loser_player, game_mode, extra)
        except Exception as e:
            print(f"⚠️ خطأ في حفظ المباراة: {e}")

def get_clean_avatar(avatar_val, fallback_name="Player"):
    # 1. إذا لم يكن هناك صورة، نرجع صورة عشوائية
    if not avatar_val or str(avatar_val).strip() == "":
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={fallback_name}"

    avatar_str = str(avatar_val).strip()
    lower = avatar_str.lower()

    # 🛡️ إصلاح أمني: نمنع البروتوكولات الخطيرة (data:, javascript:, vbscript:, إلخ)
    # حتى لو في DB قديمة فيها قيم خبيثة من قبل التحديث، نحميها هنا
    dangerous_protocols = ('data:', 'javascript:', 'vbscript:', 'file:', 'about:')
    for proto in dangerous_protocols:
        if lower.startswith(proto):
            print(f"⚠️ [SECURITY] avatar محظور: {avatar_str[:50]}")
            return f"https://api.dicebear.com/7.x/bottts/svg?seed={fallback_name}"

    # 2. الروابط الخارجية (https/http فقط)
    if lower.startswith("https://") or lower.startswith("http://"):
        return avatar_str

    # 3. معالجة الصور المرفوعة — مسار نسبي يحلّه المتصفح حسب عنوانه الحالي
    if avatar_str.startswith("/uploads/") or avatar_str.startswith("uploads/"):
        clean_path = avatar_str.replace("//uploads/", "/uploads/").lstrip("/")
        # لو BACKEND_URL مضبوط (إنتاج) نستخدمه، وإلا مسار نسبي (يعمل محلياً وعلى الجوال)
        base = settings.BACKEND_URL
        return f"{base}/{clean_path}" if base else f"/{clean_path}"

    # 4. الأفاتارات الافتراضية (نأخذ اسم الملف فقط لمنع path traversal)
    clean_name = avatar_str.split('/')[-1]
    # نتحقق من اسم الملف بشكل صارم
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+\.(svg|png|jpg|jpeg|webp)$', clean_name):
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={fallback_name}"

    # مسار نسبي للأصول — يحلّه المتصفح حسب عنوان الصفحة (لابتوب/جوال)
    base = settings.FRONTEND_URL
    return f"{base}/assets/avatars/{clean_name}" if base else f"assets/avatars/{clean_name}"

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
        # ✅ إصلاح: exact match بدل ilike fuzzy
        if not user and fallback_name and fallback_name not in ["لاعب", "مجهول", "أنت"]:
            user = db.query(User).filter(User.player_name == fallback_name.strip()).first()
            
        if not user: return default_stats
            
        huroof_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == "huroof").first()
        career_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == "career").first()
        bank_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == "bank").first()
        knowledge_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == "knowledge").first()
        user_xp = user.xp if user.xp is not None else 0
        rank = db.query(User).filter(User.xp > user_xp).count() + 1
        flag_path = f"../../assets/flags/{user.country}.svg" if user.country else default_stats["flag"]
        
        return {
            "name": user.player_name, 
            "avatar": get_clean_avatar(user.avatar, user.player_name), 
            "flag": flag_path, "rank": rank,
            "huroof": {"wins": huroof_stat.wins if huroof_stat else 0, "losses": huroof_stat.losses if huroof_stat else 0, "total": huroof_stat.matches_played if huroof_stat else 0},
            "career": {"wins": career_stat.wins if career_stat else 0, "losses": career_stat.losses if career_stat else 0, "total": career_stat.matches_played if career_stat else 0},
            "bank": {"wins": bank_stat.wins if bank_stat else 0, "losses": bank_stat.losses if bank_stat else 0, "total": bank_stat.matches_played if bank_stat else 0},
            "knowledge": {"wins": knowledge_stat.wins if knowledge_stat else 0, "losses": knowledge_stat.losses if knowledge_stat else 0, "total": knowledge_stat.matches_played if knowledge_stat else 0},
            "global": {"wins": user.wins or 0, "losses": user.losses or 0, "total": user.total_matches or 0}
        }
    except Exception as e:
        print(f"🔥 خطأ DB: {e}")
        return default_stats
    finally:
        db.close()

async def get_player_full_stats(token: str, fallback_name: str, fallback_avatar: str):
    return await asyncio.to_thread(fetch_stats_from_db, token, fallback_name, fallback_avatar)


def fetch_stats_by_user_id(target_id: int, game_mode: str = None):
    """يجلب إحصائيات لاعب عبر user_id (لفتح بروفايله من الإشعارات).
    game_mode=None → إحصائيات عامة فقط (مثل صفحة categories).
    game_mode='huroof' → إحصائيات تلك اللعبة + العامة."""
    default_stats = {
        "name": "لاعب", "avatar": get_clean_avatar("", "لاعب"),
        "flag": "../../assets/flags/SA.svg", "rank": "--",
        "game": None, "game_mode": game_mode,
        "global": {"wins": 0, "losses": 0, "total": 0}
    }
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == target_id).first()
        if not user:
            return default_stats
        user_xp = user.xp if user.xp is not None else 0
        rank = db.query(User).filter(User.xp > user_xp).count() + 1
        flag_path = f"../../assets/flags/{user.country}.svg" if user.country else default_stats["flag"]
        result = {
            "name": user.player_name,
            "avatar": get_clean_avatar(user.avatar, user.player_name),
            "flag": flag_path, "rank": rank,
            "game": None, "game_mode": game_mode,
            "global": {"wins": user.wins or 0, "losses": user.losses or 0, "total": user.total_matches or 0}
        }
        # إحصائيات لعبة محددة (لو طُلبت)
        if game_mode:
            gstat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == game_mode).first()
            result["game"] = {
                "wins": gstat.wins if gstat else 0,
                "losses": gstat.losses if gstat else 0,
                "total": gstat.matches_played if gstat else 0
            }
        return result
    except Exception as e:
        print(f"🔥 خطأ DB (by_id): {e}")
        return default_stats
    finally:
        db.close()