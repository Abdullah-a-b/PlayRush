# 🎮 Game Framework — دليل الاستخدام

## ما هذا؟

الأساس الذي تُبنى عليه **كل** ألعاب PlayRush (حروف + الـ 4 القادمة).

**الفائدة:** إضافة لعبة جديدة = ملف واحد، بدون لمس بقية النظام.

## الملفات

| الملف | الوظيفة |
|-------|---------|
| `base.py` | `BaseGame` + `BaseGameState` + `GameRegistry` |
| `trivia_example.py` | مثال يثبت أن الإطار يعمل (لعبة نمط "البنك") |
| `huroof/` | لعبة حروف (ستنتقل للإطار تدريجياً) |

## كيف تضيف لعبة جديدة (3 خطوات)

### 1. أنشئ ملف اللعبة
```python
from app.games.base import BaseGame, BaseGameState, GameRegistry

class MyGameState(BaseGameState):
    def __init__(self, room_code, players):
        super().__init__(room_code, players)
        # حقولك الخاصة هنا

    def to_dict(self): ...        # Redis-ready
    @classmethod
    def from_dict(cls, data): ...

@GameRegistry.register
class MyGame(BaseGame):
    game_mode = "my_game"

    async def create_state(...): ...
    async def on_player_action(...): ...
    # طبّق باقي الـ abstract methods
```

### 2. اللعبة تسجّل نفسها تلقائياً
بمجرد `@GameRegistry.register`، النظام يعرفها.

### 3. النظام ينشئها حسب الـ mode
```python
game = GameRegistry.create("my_game", sio)
```

## لماذا Redis-ready من اليوم؟

كل `GameState` يطبّق `to_dict()` و `from_dict()`. هذا يعني:

**الآن (in-memory):**
```python
rooms[room_code] = state  # object في الذاكرة
```

**لاحقاً (Redis، بدون إعادة كتابة اللعبة):**
```python
await redis.set(f"room:{room_code}", json.dumps(state.to_dict()))
state = MyGameState.from_dict(json.loads(await redis.get(f"room:{room_code}")))
```

نفس اللعبة، فقط مكان التخزين يتغيّر. **هذا ما يجعل الوصول لـ 5K concurrent ممكناً بدون إعادة كتابة الألعاب.**

## قاعدة ذهبية للـ scaling

⚠️ **لا تخزّن في الـ state أي شيء غير قابل للتسلسل:**
- ❌ sockets، locks، callbacks، threads
- ✅ str, int, float, bool, list, dict, None فقط

لو خزّنت object معقّد، الـ Redis migration ستنكسر لاحقاً.

## anti-cheat مدمج في الإطار

`BaseGameState` يوفّر تلقائياً:
- `is_player_in_game(sid)` — يرفض sid غير اللاعبين
- `bump_version()` — يكشف الأحداث القديمة (stale)
- `get_player(sid)` — جلب آمن

كل لعبة جديدة تحصل على هذي الحماية مجاناً.

## انتقال حروف للإطار

حروف حالياً يعمل بنظامه القديم (`HuroofGameState` في `engine.py`).
سينتقل للإطار تدريجياً — **بدون كسر اللعبة الحالية**:
1. نجعل `HuroofGameState` يرث من `BaseGameState`
2. نضيف `to_dict` / `from_dict`
3. نلفّ events في `HuroofGame(BaseGame)`

هذا يحدث في خطوة منفصلة لاحقاً عشان ما نكسر اللعبة الوحيدة الجاهزة.
