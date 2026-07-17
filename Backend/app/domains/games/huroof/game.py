"""
 HuroofGame — تسجيل لعبة حروف في إطار BaseGame (المرحلة أ من الهجرة).

هذا الملف يربط حروف بالإطار الموحّد (GameRegistry) دون لمس منطق اللعب
الموجود في events.py. الغرض من المرحلة أ:
  1. تسجيل HuroofGame في GameRegistry (النظام يعرفها رسمياً).
  2. توحيد إنشاء الحالة عبر create_state (يستخدم HuroofGameState نفسه).
  3. توفير check_win_condition + calculate_rewards كنقاط ربط للمستقبل.

 الأحداث (select/buzz/answer/help) لا تزال في events.py — تُهاجَر في المرحلة ب.
لذلك on_player_action هنا "جسر" مؤقّت لا يكسر شيئاً.
"""
from typing import Optional

from app.domains.games.base import BaseGame, GameRegistry
from app.domains.games.huroof.engine import HuroofGameState


@GameRegistry.register
class HuroofGame(BaseGame):
    """لعبة حروف ضمن الإطار الموحّد. المرحلة أ: تسجيل + حالة."""

    game_mode = "huroof"
    min_players = 2
    max_players = 2

    # ==========================================
    # إنشاء الحالة
    # ==========================================
    async def create_state(self, room_code: str, players: list) -> HuroofGameState:
        """ينشئ حالة مباراة حروف جديدة من قائمة اللاعبين.

        players: [{'sid', 'name', 'token', 'avatar'}, ...] (لاعبان)
        """
        if len(players) < 2:
            raise ValueError("حروف تتطلب لاعبَين")
        p1_sid = players[0].get('sid')
        p2_sid = players[1].get('sid')
        state = HuroofGameState(p1_sid, p2_sid, room_code=room_code, players=players)
        return state

    # ==========================================
    # دورة الحياة (جسور للمرحلة ب)
    # ==========================================
    async def on_player_join(self, state: HuroofGameState, sid: str) -> None:
        """عند عودة/انضمام لاعب. المنطق الفعلي في events.py حالياً."""
        # المرحلة ب: تُنقل إعادة المزامنة هنا.
        return None

    async def on_player_action(self, state: HuroofGameState, sid: str,
                                action_type: str, data: dict) -> dict:
        """نقطة الدخول الموحّدة لأفعال اللاعب (المرحلة ب).

        تُجري التحقق المشترك (anti-cheat الأساسي) ثم تُصنّف الفعل.
        أفعال حروف المعتمدة:
          'select_hex'    : اختيار خلية/حرف (طور الاختيار)
          'buzz'          : الضغط على الجرس (طور السؤال)
          'submit_answer' : إرسال إجابة
          'use_help'      : استخدام مساعدة
          'vote_skip'     : التصويت لتخطّي سؤال
          'surrender'     : الانسحاب

        ترجع dict: {'ok': bool, 'reason': str, 'action': str}
        التنفيذ الفعلي (mutation + emit) يبقى في معالجات events.py التي
        تستدعي هذه الدالة للتحقق المشترك — لا ازدواج منطق.
        """
        VALID_ACTIONS = {
            'select_hex', 'buzz', 'submit_answer',
            'use_help', 'vote_skip', 'surrender',
        }
        # 1) التحقق أن الفعل معروف
        if action_type not in VALID_ACTIONS:
            return {'ok': False, 'reason': 'فعل غير معروف', 'action': action_type}
        # 2) anti-cheat أساسي: اللاعب فعلاً في المباراة
        if not state.is_player_in_game(sid):
            return {'ok': False, 'reason': 'لست لاعباً في هذه المباراة', 'action': action_type}
        # 3) التحقق من المرحلة المناسبة لكل فعل
        if action_type == 'select_hex' and state.stage != 'selecting':
            return {'ok': False, 'reason': 'ليس وقت اختيار الحرف', 'action': action_type}
        if action_type in ('buzz', 'submit_answer') and state.stage == 'selecting':
            return {'ok': False, 'reason': 'اختر حرفاً أولاً', 'action': action_type}
        return {'ok': True, 'reason': '', 'action': action_type}

    def validate_action(self, state: HuroofGameState, sid: str, action_type: str) -> bool:
        """مساعد متزامن سريع للتحقق (يُستخدم في معالجات events.py)."""
        if not state.is_player_in_game(sid):
            return False
        if action_type == 'select_hex':
            return state.stage == 'selecting'
        if action_type in ('buzz', 'submit_answer'):
            return state.stage != 'selecting'
        return True

    async def on_player_leave(self, state: HuroofGameState, sid: str) -> None:
        """عند مغادرة/انقطاع لاعب. المنطق الفعلي في events.py (surrender)."""
        return None

    # ==========================================
    # شرط الفوز — منطق موحّد قابل لإعادة الاستخدام
    # ==========================================
    def check_win_condition(self, state: HuroofGameState) -> Optional[str]:
        """يتحقق هل انتهت المباراة. يرجع sid الفائز أو None.

        حروف: أول لاعب يصل points_to_win_match (افتراضياً 2 جولات) يفوز.
        """
        pts = state.points
        need = state.points_to_win_match
        # نحدّد أي لاعب يملك اللون الفائز
        # green = p1, orange = p2 (الاصطلاح المعتمد في events.py)
        if pts.get('green', 0) >= need:
            return state.p1
        if pts.get('orange', 0) >= need:
            return state.p2
        return None

    # ==========================================
    # المكافآت — تستخدم جدول حروف المعتمد (reward_service)
    # ==========================================
    async def calculate_rewards(self, state: HuroofGameState,
                                 winner_sid: str, loser_sid: str) -> dict:
        """يرجع وصف المكافآت. التنفيذ الفعلي (الخصم/الإضافة) يتم عبر
        record_match_result في events.py باستخدام نفس الجدول المعتمد."""
        winner_color = 'green' if winner_sid == state.p1 else 'orange'
        loser_color = 'orange' if winner_color == 'green' else 'green'
        return {
            'winner_sid': winner_sid,
            'loser_sid': loser_sid,
            'winner_rounds': state.points.get(winner_color, 0),
            'loser_rounds': state.points.get(loser_color, 0),
            'game_mode': 'huroof',
        }
