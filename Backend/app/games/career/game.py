"""
⚽ CareerGame — تسجيل 'مسيرة لاعب' في إطار BaseGame.

يتبع نفس نمط HuroofGame: تسجيل + create_state + check_win + calculate_rewards.
الأحداث (buzz/answer/help) في events.py.
"""
from typing import Optional

from app.games.base import BaseGame, GameRegistry
from app.games.career.engine import CareerGameState


@GameRegistry.register
class CareerGame(BaseGame):
    """لعبة 'مسيرة لاعب' — أول من يجمع 10 نقاط يفوز."""

    game_mode = "career"
    min_players = 2
    max_players = 2

    async def create_state(self, room_code: str, players: list) -> CareerGameState:
        if len(players) < 2:
            raise ValueError("مسيرة لاعب تتطلب لاعبَين")
        p1_sid = players[0].get('sid')
        p2_sid = players[1].get('sid')
        return CareerGameState(p1_sid, p2_sid, room_code=room_code, players=players)

    async def on_player_join(self, state, sid):
        return None

    async def on_player_action(self, state, sid, action_type, data):
        """نقطة دخول موحّدة (تحقق). الأفعال: buzz | submit_answer | use_help | surrender."""
        VALID = {'buzz', 'submit_answer', 'use_help', 'surrender'}
        if action_type not in VALID:
            return {'ok': False, 'reason': 'فعل غير معروف'}
        if not state.is_player_in_game(sid):
            return {'ok': False, 'reason': 'لست لاعباً في هذه المباراة'}
        if action_type == 'buzz' and not state.can_buzz(sid):
            return {'ok': False, 'reason': 'لا يمكن الضغط الآن'}
        return {'ok': True, 'reason': ''}

    async def on_player_leave(self, state, sid):
        return None

    def check_win_condition(self, state) -> Optional[str]:
        return state.check_winner()

    async def calculate_rewards(self, state, winner_sid, loser_sid) -> dict:
        return {
            'winner_sid': winner_sid,
            'loser_sid': loser_sid,
            'winner_score': state.scores.get(winner_sid, 0),
            'loser_score': state.scores.get(loser_sid, 0),
            'game_mode': 'career',
        }
