"""
🎮 BaseGame — الإطار الأساسي لكل ألعاب PlayRush

الهدف:
- كل لعبة (حروف + الـ 4 القادمة) ترث من BaseGame
- إضافة لعبة جديدة = ملف واحد يطبّق الـ abstract methods، بدون لمس بقية النظام
- مصمّم Redis-ready: كل حالة اللعبة قابلة للتسلسل (serialize) لـ dict، عشان تنتقل لـ Redis لاحقاً بسهولة

التصميم patterns:
- Template Method: BaseGame يحدّد الهيكل، الألعاب الفرعية تملأ التفاصيل
- State: كل لعبة تدير حالتها عبر stage transitions

⚠️ مهم للـ scaling: لا تخزّن أي شيء غير قابل للتسلسل في الـ state
(لا sockets، لا locks، لا callbacks). فقط بيانات JSON-safe.
عشان لما ننقل لـ Redis، الحالة تنتقل كما هي.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
import time


class BaseGameState(ABC):
    """
    الحالة الأساسية لأي لعبة.

    كل لعبة ترث وتضيف حقولها الخاصة.
    شرط Redis-ready: كل الحقول يجب أن تكون JSON-serializable
    (str, int, float, bool, list, dict, None — لا objects معقدة).
    """

    def __init__(self, room_code: str, players: list[dict]):
        # بيانات مشتركة لكل الألعاب
        self.room_code = room_code
        self.players = players          # [{'sid', 'name', 'token', 'avatar'}, ...]
        self.stage = 'waiting'          # حالة اللعبة الحالية
        self.created_at = time.time()
        self.state_version = 0          # للكشف عن stale updates (anti-cheat)
        self.winner = None              # sid الفائز عند الانتهاء

    def bump_version(self) -> int:
        """يزيد رقم النسخة — يُستخدم لرفض الأحداث القديمة (anti-cheat)."""
        self.state_version += 1
        return self.state_version

    def get_player(self, sid: str) -> Optional[dict]:
        """يجلب بيانات لاعب بالـ sid."""
        for p in self.players:
            if p.get('sid') == sid:
                return p
        return None

    def is_player_in_game(self, sid: str) -> bool:
        """يتحقق أن الـ sid لاعب فعلي في هذه المباراة (anti-cheat أساسي)."""
        return any(p.get('sid') == sid for p in self.players)

    # ==========================================
    # Redis-ready serialization
    # ==========================================
    @abstractmethod
    def to_dict(self) -> dict:
        """
        يحوّل الحالة لـ dict قابل للتخزين في Redis.
        كل لعبة تطبّقها لتشمل حقولها الخاصة.
        """
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "BaseGameState":
        """يعيد بناء الحالة من dict (من Redis)."""
        ...


class BaseGame(ABC):
    """
    الإطار الأساسي لكل لعبة.

    كل لعبة تطبّق:
    - الأحداث (on_player_join, on_player_action, on_player_leave)
    - حساب المكافآت (calculate_rewards)
    - شروط الفوز (check_win_condition)

    الـ sio (Socket.IO server) يُمرّر للـ constructor — لكن لا يُخزّن في الـ state
    (عشان الـ state يبقى Redis-ready).
    """

    # معرّف اللعبة الفريد — كل لعبة تحدده
    game_mode: str = "base"
    # عدد اللاعبين المطلوب
    min_players: int = 2
    max_players: int = 2

    def __init__(self, sio):
        self.sio = sio  # Socket.IO server — للبثّ فقط، لا يُخزّن في state

    # ==========================================
    # دورة حياة المباراة (Template Method)
    # ==========================================

    @abstractmethod
    async def create_state(self, room_code: str, players: list[dict]) -> BaseGameState:
        """ينشئ حالة مباراة جديدة."""
        ...

    @abstractmethod
    async def on_player_join(self, state: BaseGameState, sid: str) -> None:
        """عند انضمام/عودة لاعب."""
        ...

    @abstractmethod
    async def on_player_action(self, state: BaseGameState, sid: str,
                                action_type: str, data: dict) -> None:
        """
        عند فعل لاعب (buzz, answer, select, إلخ).

        ⚠️ كل لعبة مسؤولة عن:
        1. التحقق أن sid لاعب فعلي (state.is_player_in_game)
        2. التحقق أن الـ stage يسمح بهذا الفعل
        3. anti-cheat validation
        """
        ...

    @abstractmethod
    async def on_player_leave(self, state: BaseGameState, sid: str) -> None:
        """عند مغادرة/انقطاع لاعب."""
        ...

    @abstractmethod
    def check_win_condition(self, state: BaseGameState) -> Optional[str]:
        """
        يتحقق من شرط الفوز.
        يرجع sid الفائز، أو None لو ما انتهت.
        """
        ...

    @abstractmethod
    async def calculate_rewards(self, state: BaseGameState,
                                 winner_sid: str, loser_sid: str) -> dict:
        """
        يحسب المكافآت (XP, coins, gems).
        يرجع dict بالمكافآت لكل لاعب.
        """
        ...

    # ==========================================
    # helpers مشتركة
    # ==========================================

    async def broadcast(self, room_code: str, event: str, data: Any) -> None:
        """يبثّ حدثاً لكل اللاعبين في الغرفة."""
        await self.sio.emit(event, data, room=room_code)

    async def send_to_player(self, sid: str, event: str, data: Any) -> None:
        """يرسل حدثاً للاعب واحد."""
        await self.sio.emit(event, data, to=sid)


# ==========================================
# Game Registry — يسجّل كل الألعاب المتاحة
# ==========================================
class GameRegistry:
    """
    سجلّ مركزي لكل الألعاب.

    كل لعبة تُسجّل نفسها هنا. النظام يستخدم الـ registry
    لإنشاء اللعبة الصحيحة حسب game_mode بدون if/else طويلة.

    Pattern: Registry + Factory
    """
    _games: dict[str, type[BaseGame]] = {}

    @classmethod
    def register(cls, game_class: type[BaseGame]) -> type[BaseGame]:
        """
        decorator لتسجيل لعبة:

        @GameRegistry.register
        class HuroofGame(BaseGame):
            game_mode = "huroof"
        """
        cls._games[game_class.game_mode] = game_class
        return game_class

    @classmethod
    def get(cls, game_mode: str) -> Optional[type[BaseGame]]:
        """يجلب class اللعبة حسب الـ mode."""
        return cls._games.get(game_mode)

    @classmethod
    def create(cls, game_mode: str, sio) -> Optional[BaseGame]:
        """ينشئ instance من اللعبة المطلوبة."""
        game_class = cls._games.get(game_mode)
        if not game_class:
            return None
        return game_class(sio)

    @classmethod
    def all_modes(cls) -> list[str]:
        """كل الألعاب المسجّلة."""
        return list(cls._games.keys())
