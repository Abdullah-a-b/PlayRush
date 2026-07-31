"""محاكاة Monte Carlo لتوازن بوت الوضع الفردي — مسيرة لاعب.

سكربت مؤقّت (بلا DB/Socket.IO) يستورد solo_bot.py مباشرة ويحاكي مئات
المباريات الوهمية ضد "لاعب بشري" مبسّط، لكل مستوى صعوبة، ويطبع معدل فوز
البوت وتوقيت البزّ ومعدل استخدام المساعدات — عشان نتأكد بالعين إن كل
مستوى صعوبة أصعب فعلياً من اللي قبله قبل ربط البوت بالخادم الحقيقي.

الاستخدام من مجلد Backend:
    python scripts/career_solo_bot_sim.py
"""
import os
import random
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # يمنع تشويه العربي على كونسول ويندوز

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

from app.domains.games.career import solo_bot as bot  # noqa: E402

TOTAL_PLAYERS = 5
ANSWER_WINDOW = 10
MAX_STRIKES = 2
MAX_CLUBS = 10
FINAL_EXTRA_TICKS = 2   # تكات إضافية بعد آخر نادٍ (تمثيل مبسّط لـFINAL_WINDOW)

# "لاعب بشري" مبسّط — مو نموذجاً دقيقاً، بس أساس ثابت للمقارنة بين الصعوبات
HUMAN = {
    'know_prob': 0.62,
    'buzz_prob_per_tick_knows': 0.30,   # احتمال بزّ بكل تكة لو يعرف (من النادي 2)
    'buzz_prob_per_tick_blind': 0.05,   # بزّة يائسة لو ما يعرف (من النادي 4)
    'accuracy_knows': 0.82,
    'accuracy_blind': 0.15,
    'delay_range': (0.5, 3.0),
}


def _simulate_personality(difficulty):
    """يُرجع ('bot'|'human'|None, buzz_tick|None, bot_used_help:bool)."""
    clubs = random.randint(1, MAX_CLUBS)
    single_club = clubs == 1

    bot_knows = bot.bot_knows_player(difficulty)
    jitter = bot.new_player_jitter()
    human_knows = random.random() < HUMAN['know_prob']

    loadout = bot.bot_loadout(difficulty)
    used_this_player = set()
    bot_strikes = 0
    human_strikes = 0
    bot_used_help = False

    max_ticks = clubs + FINAL_EXTRA_TICKS
    for revealed in range(1, max_ticks + 1):
        career_complete = revealed >= clubs
        # تقريب first_reveal_done: أول تكة بعد اكتمال المسيرة
        is_final = career_complete and revealed > clubs if not single_club else revealed > 1

        # -- قرار مساعدة البوت (مرة واحدة تقريباً لكل شخصية) --
        if bot_strikes < MAX_STRIKES:
            available = [h for h in loadout if h not in used_this_player]
            hid = bot.decide_help(difficulty, bot_knows, revealed, bot_strikes,
                                   available, used_this_player, jitter,
                                   single_club, is_final)
            if hid:
                used_this_player.add(hid)
                bot_used_help = True

        conf_bonus = bot.help_conf_bonus(used_this_player)
        accuracy_bonus = bot.help_accuracy_bonus(used_this_player)
        has_shield = bot.has_shield(used_this_player)

        bot_will_buzz = False
        bot_decision = None
        if bot_strikes < MAX_STRIKES:
            bot_decision = bot.decide_full(
                difficulty, bot_knows, revealed, bot_strikes, ANSWER_WINDOW,
                jitter, human_strikes >= MAX_STRIKES, is_final, single_club,
                conf_bonus, has_shield, accuracy_bonus)
            bot_will_buzz = bot_decision['will_buzz']

        # -- نموذج بشري مبسّط --
        human_will_buzz = False
        human_delay = 99
        if human_strikes < MAX_STRIKES and revealed >= 2:
            if human_knows and random.random() < HUMAN['buzz_prob_per_tick_knows']:
                human_will_buzz = True
            elif not human_knows and revealed >= 4 and random.random() < HUMAN['buzz_prob_per_tick_blind']:
                human_will_buzz = True
            if human_will_buzz:
                human_delay = round(random.uniform(*HUMAN['delay_range']), 2)

        if not bot_will_buzz and not human_will_buzz:
            continue

        # من يبزّ أولاً هذي التكة (الأقل تأخيراً)
        bot_delay = bot_decision['buzz_delay'] if bot_will_buzz else 99
        winner = 'bot' if bot_delay <= human_delay else 'human'
        if winner == 'bot':
            correct = bot_decision['correct']
        else:
            correct = random.random() < (HUMAN['accuracy_knows'] if human_knows
                                          else HUMAN['accuracy_blind'])

        if correct:
            return winner, revealed, bot_used_help
        # خطأ: سترايك لهذا الطرف، يكمل السباق للطرف الآخر
        if winner == 'bot':
            bot_strikes += 1
        else:
            human_strikes += 1
        if bot_strikes >= MAX_STRIKES and human_strikes >= MAX_STRIKES:
            return None, None, bot_used_help

    return None, None, bot_used_help  # لا أحد أجاب — تُستبدل الشخصية


def simulate_match(difficulty):
    bot_score = 0
    human_score = 0
    buzz_ticks = []
    help_uses = 0
    for _ in range(TOTAL_PLAYERS):
        winner, tick, used_help = _simulate_personality(difficulty)
        if used_help:
            help_uses += 1
        if winner == 'bot':
            bot_score += 1
            buzz_ticks.append(tick)
        elif winner == 'human':
            human_score += 1
    return bot_score, human_score, buzz_ticks, help_uses


def main(n_matches=500):
    print("=" * 60)
    print("محاكاة توازن بوت الوضع الفردي — مسيرة لاعب")
    print("=" * 60)
    for difficulty in bot.DIFFICULTIES:
        bot_wins = 0
        ties = 0
        all_ticks = []
        total_help_uses = 0
        for _ in range(n_matches):
            bs, hs, ticks, help_uses = simulate_match(difficulty)
            if bs > hs:
                bot_wins += 1
            elif bs == hs:
                ties += 1
            all_ticks.extend(ticks)
            total_help_uses += help_uses

        win_rate = 100.0 * bot_wins / n_matches
        tie_rate = 100.0 * ties / n_matches
        avg_tick = (sum(all_ticks) / len(all_ticks)) if all_ticks else 0.0
        avg_help = total_help_uses / (n_matches * TOTAL_PLAYERS)

        label = bot.get_difficulty(difficulty)['label']
        print(f"\n[{difficulty:9s}] ({label})")
        print(f"  فوز البوت: {win_rate:5.1f}%   تعادل: {tie_rate:4.1f}%")
        print(f"  متوسط نادٍ يبزّ عنده البوت: {avg_tick:.1f}")
        print(f"  معدل استخدام مساعدة لكل شخصية: {avg_help:.2f}")

    print("\n" + "-" * 60)
    print("توقّع منطقي: فوز البوت يتصاعد beginner < medium < hard < expert.")
    print("لو ما تصاعد بوضوح، راجع عتبات thresh_first/thresh_second في solo_bot.py.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    main(n)
