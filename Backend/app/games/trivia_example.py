"""
🏦 مثال: لعبة Trivia بسيطة (نمط "البنك")

⚠️ هذا ملف توضيحي يثبت أن الـ BaseGame framework يعمل.
إضافة لعبة جديدة = هذا الحجم تقريباً، بدون لمس بقية النظام.

يوضح:
- كيف ترث لعبة من BaseGame
- كيف تسجّل نفسها في GameRegistry
- كيف تكون Redis-ready (to_dict / from_dict)
"""
import random
import time
from typing import Optional

from app.games.base import BaseGame, BaseGameState, GameRegistry


class TriviaGameState(BaseGameState):
    """حالة مباراة trivia."""

    def __init__(self, room_code: str, players: list[dict]):
        super().__init__(room_code, players)
        self.stage = 'playing'
        self.scores = {p['sid']: 0 for p in players}   # نقاط كل لاعب
        self.current_question = None                    # السؤال الحالي
        self.question_number = 0
        self.max_questions = 10                         # 10 أسئلة للفوز
        self.questions_to_win = 6                       # 6 إجابات صحيحة = فوز
        self.question_shown_at = None                   # للـ anti-cheat (reaction time)
        self.answered_by = []                           # من أجاب هذا السؤال

    def to_dict(self) -> dict:
        """Redis-ready: كل الحقول JSON-safe."""
        return {
            'room_code': self.room_code,
            'players': self.players,
            'stage': self.stage,
            'created_at': self.created_at,
            'state_version': self.state_version,
            'winner': self.winner,
            'scores': self.scores,
            'current_question': self.current_question,
            'question_number': self.question_number,
            'max_questions': self.max_questions,
            'questions_to_win': self.questions_to_win,
            'question_shown_at': self.question_shown_at,
            'answered_by': self.answered_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TriviaGameState":
        """يعيد البناء من Redis."""
        state = cls(data['room_code'], data['players'])
        state.stage = data['stage']
        state.created_at = data['created_at']
        state.state_version = data['state_version']
        state.winner = data['winner']
        state.scores = data['scores']
        state.current_question = data['current_question']
        state.question_number = data['question_number']
        state.max_questions = data['max_questions']
        state.questions_to_win = data['questions_to_win']
        state.question_shown_at = data['question_shown_at']
        state.answered_by = data['answered_by']
        return state


@GameRegistry.register
class TriviaGame(BaseGame):
    """لعبة trivia تنافسية — أول من يصل 6 إجابات صحيحة يفوز."""

    game_mode = "trivia"
    min_players = 2
    max_players = 2

    async def create_state(self, room_code: str, players: list[dict]) -> TriviaGameState:
        return TriviaGameState(room_code, players)

    async def on_player_join(self, state: TriviaGameState, sid: str) -> None:
        await self.broadcast(state.room_code, 'player_ready', {'sid': sid})

    async def on_player_action(self, state: TriviaGameState, sid: str,
                                action_type: str, data: dict) -> None:
        # 🛡️ anti-cheat الأساسي (موروث من الإطار)
        if not state.is_player_in_game(sid):
            return  # sid ليس لاعباً فعلياً — تجاهل

        if action_type == 'submit_answer':
            await self._handle_answer(state, sid, data)

    async def _handle_answer(self, state: TriviaGameState, sid: str, data: dict) -> None:
        # تحقق من الـ stage
        if state.stage != 'playing':
            return
        # تحقق أن اللاعب ما أجاب هذا السؤال
        if sid in state.answered_by:
            return

        # 🛡️ anti-cheat: reaction time (سيستفيد من نظام anticheat لاحقاً)
        if state.question_shown_at:
            reaction = time.time() - state.question_shown_at
            if reaction < 0.08:  # أسرع من بشري ممكن
                return  # bot detected

        answer = str(data.get('answer', '')).strip()
        correct = state.current_question.get('answer', '') if state.current_question else ''

        # هنا لاحقاً: نستخدم نظام فحص الإجابات (Normalize → Fuzzy → AI)
        is_correct = (answer.lower() == correct.lower())

        state.answered_by.append(sid)

        if is_correct:
            state.scores[sid] += 1
            state.bump_version()
            await self.broadcast(state.room_code, 'correct_answer', {
                'sid': sid, 'scores': state.scores
            })

    async def on_player_leave(self, state: TriviaGameState, sid: str) -> None:
        # اللاعب الآخر يفوز بالانسحاب
        state.stage = 'finished'
        remaining = [p['sid'] for p in state.players if p['sid'] != sid]
        if remaining:
            state.winner = remaining[0]

    def check_win_condition(self, state: TriviaGameState) -> Optional[str]:
        for sid, score in state.scores.items():
            if score >= state.questions_to_win:
                return sid
        return None

    async def calculate_rewards(self, state: TriviaGameState,
                                 winner_sid: str, loser_sid: str) -> dict:
        return {
            winner_sid: {'xp': 150, 'coins': 100, 'gems': 0},
            loser_sid: {'xp': 50, 'coins': 0, 'gems': 0},
        }
