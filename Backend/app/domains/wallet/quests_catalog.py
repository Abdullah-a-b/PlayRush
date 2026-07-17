"""
quests_catalog.py — قوالب المهام (يومية/أسبوعية/موسمية).

المكافآت (من قرار الاقتصاد):
- يومية: كوينز + XP فقط (لا جواهر — تحمي ندرتها) + Pass XP.
- أسبوعية: كوينز + XP + جواهر + Pass XP.
- موسمية: أكبر — جواهر أعلى + Pass XP كبير.

الأحداث التي تحرّك التقدّم (event keys):
  match_played      — أي مباراة مكتملة
  match_won         — فوز
  game_played:<mode>— مباراة في لعبة محددة
  correct_answer    — إجابة صحيحة (تُبثّ من الألعاب)
  help_used         — استخدام مساعدة
  buzz_correct      — جرس + إجابة صحيحة (مسيرة/من أنا)
  perfect_huroof    — فوز حروف 2-0
  distinct_games    — عدد الألعاب المختلفة الملعوبة (يُحسب دورياً)
"""

# reward: coins / xp / gems / pass_xp
DAILY_TEMPLATES = [
    {"key": "d_play_3", "event": "match_played", "target": 3,
     "title": "العب 3 مباريات", "icon": "🎮",
     "reward": {"coins": 60, "xp": 30, "pass_xp": 20}},
    {"key": "d_win_2", "event": "match_won", "target": 2,
     "title": "افز بمباراتين", "icon": "🏆",
     "reward": {"coins": 80, "xp": 40, "pass_xp": 25}},
    {"key": "d_correct_15", "event": "correct_answer", "target": 15,
     "title": "أجب 15 إجابة صحيحة", "icon": "✅",
     "reward": {"coins": 50, "xp": 25, "pass_xp": 15}},
    {"key": "d_two_games", "event": "distinct_games", "target": 2,
     "title": "العب لعبتين مختلفتين", "icon": "🎲",
     "reward": {"coins": 50, "xp": 30, "pass_xp": 20}},
    {"key": "d_use_help", "event": "help_used", "target": 2,
     "title": "استخدم مساعدتين", "icon": "🎯",
     "reward": {"coins": 40, "xp": 20, "pass_xp": 15}},
    {"key": "d_buzz", "event": "buzz_correct", "target": 3,
     "title": "3 إجابات صحيحة بالجرس", "icon": "🔔",
     "reward": {"coins": 60, "xp": 30, "pass_xp": 20}},
]

WEEKLY_TEMPLATES = [
    {"key": "w_play_20", "event": "match_played", "target": 20,
     "title": "العب 20 مباراة هذا الأسبوع", "icon": "🎮",
     "reward": {"coins": 300, "xp": 150, "gems": 10, "pass_xp": 100}},
    {"key": "w_win_10", "event": "match_won", "target": 10,
     "title": "افز بـ10 مباريات", "icon": "👑",
     "reward": {"coins": 350, "xp": 180, "gems": 12, "pass_xp": 120}},
    {"key": "w_all_games", "event": "distinct_games", "target": 5,
     "title": "العب كل الألعاب الخمس", "icon": "🌟",
     "reward": {"coins": 250, "xp": 150, "gems": 10, "pass_xp": 100}},
    {"key": "w_correct_80", "event": "correct_answer", "target": 80,
     "title": "أجب 80 إجابة صحيحة", "icon": "🧠",
     "reward": {"coins": 280, "xp": 140, "gems": 8, "pass_xp": 90}},
    {"key": "w_perfect_3", "event": "perfect_huroof", "target": 3,
     "title": "3 انتصارات كاسحة في حروف (2-0)", "icon": "🔥",
     "reward": {"coins": 300, "xp": 160, "gems": 10, "pass_xp": 110}},
]

SEASONAL_TEMPLATES = [
    {"key": "s_play_100", "event": "match_played", "target": 100,
     "title": "العب 100 مباراة هذا الموسم", "icon": "🎮",
     "reward": {"coins": 1000, "xp": 500, "gems": 30, "pass_xp": 300}},
    {"key": "s_win_50", "event": "match_won", "target": 50,
     "title": "افز بـ50 مباراة", "icon": "🏅",
     "reward": {"coins": 1200, "xp": 600, "gems": 40, "pass_xp": 400}},
    {"key": "s_correct_500", "event": "correct_answer", "target": 500,
     "title": "أجب 500 إجابة صحيحة", "icon": "📚",
     "reward": {"coins": 800, "xp": 500, "gems": 25, "pass_xp": 300}},
    {"key": "s_master_game", "event": "game_won:any", "target": 25,
     "title": "أتقن لعبة: 25 فوزاً في أي لعبة", "icon": "🎓",
     "reward": {"coins": 900, "xp": 450, "gems": 30, "pass_xp": 350}},
]


def all_by_scope(scope: str):
    return {"daily": DAILY_TEMPLATES, "weekly": WEEKLY_TEMPLATES,
            "seasonal": SEASONAL_TEMPLATES}.get(scope, [])


def template_for(quest_key: str):
    for lst in (DAILY_TEMPLATES, WEEKLY_TEMPLATES, SEASONAL_TEMPLATES):
        for t in lst:
            if t["key"] == quest_key:
                return t
    return None
