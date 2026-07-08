"""
🏦 BankGame — تسجيل 'البنك' في إطار BaseGame.
"""
from typing import Optional

from app.games.base import BaseGame, GameRegistry
from app.games.bank.engine import BankGameState


@GameRegistry.register
class BankGame(BaseGame):
    """لعبة 'البنك' — أدوار فردية، 3 جولات، الأعلى رصيداً آمناً يفوز."""

    game_mode = "bank"
    min_players = 2
    max_players = 2

    async def create_state(self, room_code: str, players: list) -> BankGameState:
        if len(players) < 2:
            raise ValueError("البنك يتطلب لاعبَين")
        return BankGameState(players[0].get('sid'), players[1].get('sid'),
                             room_code=room_code, players=players)

    async def on_player_join(self, state, sid):
        return None

    def check_win_condition(self, state) -> Optional[str]:
        return state.winner

    def calculate_rewards(self, state, winner_sid, loser_sid) -> dict:
        return {
            'winner_score': state.safe.get(winner_sid, 0),
            'loser_score': state.safe.get(loser_sid, 0),
        }
