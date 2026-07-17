"""
WhoamiGame — تسجيل «من أنا» في إطار BaseGame.

نفس نمط CareerGame: تسجيل + create_state + check_win + calculate_rewards.
الأحداث (buzz/submit/surrender) في events.py.
"""
from typing import Optional

from app.domains.games.base import BaseGame, GameRegistry
from app.domains.games.whoami.engine import WhoamiGameState


@GameRegistry.register
class WhoamiGame(BaseGame):
    """لعبة «من أنا» — 5 شخصيات، الأعلى نقاطاً يفوز."""

    game_mode = "whoami"
    min_players = 2
    max_players = 2

    async def create_state(self, room_code: str, players: list) -> WhoamiGameState:
        if len(players) < 2:
            raise ValueError("من أنا تتطلب لاعبَين")
        p1_sid = players[0].get('sid')
        p2_sid = players[1].get('sid')
        return WhoamiGameState(p1_sid, p2_sid, room_code=room_code, players=players)

    async def on_player_join(self, state, sid):
        return None

    async def on_player_action(self, state, sid, action_type, data):
        VALID = {'buzz', 'submit_answer', 'surrender'}
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
        if state.stage == 'finished':
            return state.winner
        return None

    async def calculate_rewards(self, state, winner_sid, loser_sid) -> dict:
        return {
            'winner_sid': winner_sid,
            'loser_sid': loser_sid,
            'winner_score': state.scores.get(winner_sid, 0),
            'loser_score': state.scores.get(loser_sid, 0),
            'game_mode': 'whoami',
        }
