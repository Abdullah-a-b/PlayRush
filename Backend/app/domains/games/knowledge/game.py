"""
 KnowledgeGame — تسجيل "ماذا تعرف" في إطار BaseGame.
"""
from typing import Optional

from app.domains.games.base import BaseGame, GameRegistry
from app.domains.games.knowledge.engine import KnowledgeGameState


@GameRegistry.register
class KnowledgeGame(BaseGame):
    """لعبة 'ماذا تعرف' — نفس السؤال للطرفين معاً، سرعة + دقة."""

    game_mode = "knowledge"
    min_players = 2
    max_players = 2

    async def create_state(self, room_code: str, players: list) -> KnowledgeGameState:
        if len(players) < 2:
            raise ValueError("ماذا تعرف تتطلب لاعبَين")
        return KnowledgeGameState(players[0].get('sid'), players[1].get('sid'),
                                  room_code=room_code, players=players)

    async def on_player_join(self, state, sid):
        return None

    def check_win_condition(self, state) -> Optional[str]:
        return state.winner

    def calculate_rewards(self, state, winner_sid, loser_sid) -> dict:
        return {
            'winner_score': state.scores.get(winner_sid, 0),
            'loser_score': state.scores.get(loser_sid, 0),
        }
