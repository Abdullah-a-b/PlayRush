"""
quests_service.py — توليد المهام وتتبّع تقدّمها واستلام مكافآتها.

- المهام تُولَّد كسولاً عند أول طلب في الفترة (يومي/أسبوعي/موسمي).
- اليومية 3 عشوائية من القوالب، الأسبوعية 3، الموسمية كلها.
- حدث اللعب يحرّك التقدّم عبر progress_event().
- الاستلام يمنح المكافآت مرة واحدة (claimed).
"""
import json
import random
import datetime

from sqlalchemy.orm import Session

from app.domains.wallet import quests_catalog as QC
from app.domains.wallet import economy_config as EC
from app.domains.wallet.period_keys import daily_key, weekly_key, season_key
from app.domains.wallet.progression_models import PlayerQuest
from app.domains.wallet.pass_service import add_pass_xp


def _period_for(scope: str) -> str:
    return {"daily": daily_key(), "weekly": weekly_key(),
            "seasonal": season_key()}.get(scope, daily_key())


def _slots_for(scope: str) -> int:
    return {"daily": EC.DAILY_QUEST_SLOTS, "weekly": EC.WEEKLY_QUEST_SLOTS,
            "seasonal": EC.SEASONAL_QUEST_SLOTS}.get(scope, 3)


def ensure_quests(db: Session, user_id: int, scope: str):
    """يولّد مهام الفترة الحالية لهذا النطاق إن لم تكن موجودة."""
    period = _period_for(scope)
    existing = (db.query(PlayerQuest)
                  .filter(PlayerQuest.user_id == user_id,
                          PlayerQuest.scope == scope,
                          PlayerQuest.period_key == period)
                  .all())
    if existing:
        return existing

    templates = QC.all_by_scope(scope)
    slots = min(_slots_for(scope), len(templates))
    # بذرة ثابتة لكل (لاعب+فترة) حتى لا تتغير المهام عند إعادة التحميل
    seed = hash(f"{user_id}:{scope}:{period}") & 0xFFFFFFFF
    rnd = random.Random(seed)
    chosen = templates if scope == "seasonal" else rnd.sample(templates, slots)

    created = []
    for t in chosen:
        q = PlayerQuest(
            user_id=user_id, quest_key=t["key"], scope=scope,
            period_key=period, target=t["target"], progress=0, claimed=False,
        )
        db.add(q)
        created.append(q)
    db.commit()
    return created


def get_quests(db: Session, user_id: int) -> dict:
    """كل مهام اللاعب النشطة مع قوالبها للعرض."""
    out = {}
    for scope in ("daily", "weekly", "seasonal"):
        rows = ensure_quests(db, user_id, scope)
        items = []
        for q in rows:
            t = QC.template_for(q.quest_key) or {}
            items.append({
                "key": q.quest_key, "scope": scope,
                "title": t.get("title", q.quest_key), "icon": t.get("icon", "🎯"),
                "target": q.target, "progress": min(q.progress, q.target),
                "done": q.progress >= q.target, "claimed": q.claimed,
                "reward": t.get("reward", {}),
            })
        out[scope] = items
    return out


def progress_event(db: Session, user_id: int, event: str, amount: int = 1,
                   meta: dict = None) -> list:
    """يحرّك تقدّم كل المهام النشطة المطابقة للحدث. يرجع المهام المكتملة حديثاً."""
    meta = meta or {}
    newly_done = []
    for scope in ("daily", "weekly", "seasonal"):
        rows = ensure_quests(db, user_id, scope)
        for q in rows:
            if q.claimed or q.progress >= q.target:
                continue
            t = QC.template_for(q.quest_key)
            if not t:
                continue
            ev = t["event"]
            match = False
            if ev == event:
                match = True
            elif ev.startswith("game_played:") and event == "game_played" \
                    and ev.split(":", 1)[1] in ("any", meta.get("game_mode")):
                match = True
            elif ev.startswith("game_won:") and event == "game_won" \
                    and ev.split(":", 1)[1] in ("any", meta.get("game_mode")):
                match = True
            elif ev == "distinct_games" and event == "distinct_games":
                # التقدّم = العدد المطلق (لا تراكمي)
                q.progress = max(q.progress, amount)
                if q.progress >= q.target:
                    newly_done.append(q.quest_key)
                continue
            if match:
                q.progress += amount
                if q.progress >= q.target:
                    newly_done.append(q.quest_key)
    db.commit()
    return newly_done


def claim_quest(db: Session, user_id: int, quest_key: str) -> dict:
    """يستلم مكافأة مهمة مكتملة (مرة واحدة). يرجع المكافآت المطبّقة."""
    period_candidates = [daily_key(), weekly_key(), season_key()]
    q = (db.query(PlayerQuest)
           .filter(PlayerQuest.user_id == user_id,
                   PlayerQuest.quest_key == quest_key,
                   PlayerQuest.period_key.in_(period_candidates))
           .first())
    if not q:
        return {"ok": False, "msg": "المهمة غير موجودة"}
    if q.progress < q.target:
        return {"ok": False, "msg": "المهمة غير مكتملة بعد"}
    if q.claimed:
        return {"ok": False, "msg": "استلمتها مسبقاً"}

    t = QC.template_for(quest_key) or {}
    reward = t.get("reward", {})

    from app.domains.users.models import User
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        return {"ok": False, "msg": "المستخدم غير موجود"}

    applied = {"coins": 0, "xp": 0, "gems": 0, "pass_xp": 0}
    if reward.get("coins"):
        user.coins = (user.coins or 0) + reward["coins"]; applied["coins"] = reward["coins"]
    if reward.get("xp"):
        user.xp = (user.xp or 0) + reward["xp"]; applied["xp"] = reward["xp"]
    if reward.get("gems"):
        user.gems = (user.gems or 0) + reward["gems"]; applied["gems"] = reward["gems"]
    q.claimed = True
    db.commit()

    if reward.get("pass_xp"):
        add_pass_xp(db, user_id, reward["pass_xp"])
        applied["pass_xp"] = reward["pass_xp"]

    return {"ok": True, "reward": applied, "title": t.get("title", quest_key)}
