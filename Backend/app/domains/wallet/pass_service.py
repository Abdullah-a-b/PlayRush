"""
pass_service.py — الـPass الموسمي (نموذج Brawl Stars).

- Pass XP منفصل تماماً عن XP الليفل وElo.
- 30 محطة، كل 100 Pass XP محطة.
- مساران: مجاني (للجميع) + Premium (يُشترى بالجواهر مرة، يموّل نفسه).
- reset تلقائي كل موسم (صف جديد لكل season_key).
"""
import json

from sqlalchemy.orm import Session

from app.domains.wallet import economy_config as EC
from app.domains.wallet.period_keys import season_key
from app.domains.wallet.progression_models import PlayerPass


# ============================================================
#  جوائز محطات الـPass — تُبنى مرة (متوازنة حسابياً)
# ============================================================
def _build_pass_rewards():
    """يبني جوائز الـ30 محطة لكل مسار.

    المجاني: كوينز غالباً + جواهر متفرّقة (مجموع ~30 جوهرة/موسم).
    Premium: أغنى + مجموع جواهر PREMIUM_PASS_GEM_PAYBACK (يموّل نفسه).
    """
    free, premium = [], []
    # نوزّع جواهر Premium على المحطات بحيث يبلغ المجموع payback
    premium_gem_tiers = [5, 10, 15, 20, 25, 30]  # المحطات التي تمنح جواهر
    gem_each = EC.PREMIUM_PASS_GEM_PAYBACK // len(premium_gem_tiers)
    free_gem_tiers = {10: 10, 20: 10, 30: 10}     # مجاني: 30 جوهرة على 3 محطات

    for tier in range(1, EC.PASS_TIERS + 1):
        # المجاني
        if tier in free_gem_tiers:
            free.append({"type": "gems", "amount": free_gem_tiers[tier], "icon": "💎"})
        elif tier % 5 == 0:
            free.append({"type": "coins", "amount": 150, "icon": "🪙"})
        else:
            free.append({"type": "coins", "amount": 60, "icon": "🪙"})
        # Premium
        if tier in premium_gem_tiers:
            premium.append({"type": "gems", "amount": gem_each, "icon": "💎"})
        elif tier in (9, 19, 29):
            premium.append({"type": "cosmetic", "amount": 1, "icon": "🎨",
                            "item_id": {9:"avatar_16", 19:"avatar_17", 29:"avatar_18"}[tier], "note": "أفاتار"})
        elif tier in (4, 14, 24):
            premium.append({"type": "coins", "amount": 250, "icon": "🪙"})
        else:
            premium.append({"type": "coins", "amount": 120, "icon": "🪙"})
    return free, premium


FREE_REWARDS, PREMIUM_REWARDS = _build_pass_rewards()
# Existing November passes keep the rewards displayed when they were sold.
def premium_rewards(season):
    if season >= "2026-S12":
        return PREMIUM_REWARDS
    return [reward if i % 5 == 0 else {"type":"coins","amount":120,"icon":"🪙"}
            for i,reward in enumerate(PREMIUM_REWARDS,1)]



def get_or_create_pass(db: Session, user_id: int) -> PlayerPass:
    from app.domains.users.models import User
    db.query(User.id).filter(User.id == user_id).with_for_update().one()
    skey = season_key()
    p = (db.query(PlayerPass).populate_existing()
           .filter(PlayerPass.user_id == user_id, PlayerPass.season_key == skey)
           .first())
    if not p:
        p = PlayerPass(user_id=user_id, season_key=skey, pass_xp=0,
                       is_premium=False, claimed_free="[]", claimed_premium="[]")
        db.add(p)
        db.flush()
    return p


def _tier_from_xp(pass_xp: int) -> int:
    """المحطة الحالية (0..PASS_TIERS)."""
    return min(EC.PASS_TIERS, pass_xp // EC.PASS_XP_PER_TIER)


def add_pass_xp(db: Session, user_id: int, amount: int) -> dict:
    if amount <= 0:
        return {"added": 0}
    p = get_or_create_pass(db, user_id)
    before = _tier_from_xp(p.pass_xp)
    p.pass_xp = (p.pass_xp or 0) + amount
    after = _tier_from_xp(p.pass_xp)
    db.flush()
    return {"added": amount, "pass_xp": p.pass_xp,
            "tier_before": before, "tier_after": after,
            "tiers_gained": after - before}


def get_pass_state(db: Session, user_id: int) -> dict:
    p = get_or_create_pass(db, user_id)
    tier = _tier_from_xp(p.pass_xp)
    in_tier = p.pass_xp - tier * EC.PASS_XP_PER_TIER
    claimed_free = set(json.loads(p.claimed_free or "[]"))
    claimed_premium = set(json.loads(p.claimed_premium or "[]"))

    premium = premium_rewards(p.season_key)
    tiers = []
    for i in range(1, EC.PASS_TIERS + 1):
        tiers.append({
            "tier": i,
            "unlocked": i <= tier,
            "free": FREE_REWARDS[i - 1],
            "free_claimed": i in claimed_free,
            "premium": premium[i - 1],
            "premium_claimed": i in claimed_premium,
        })

    return {
        "season": season_key(),
        "pass_xp": p.pass_xp,
        "current_tier": tier,
        "total_tiers": EC.PASS_TIERS,
        "xp_in_tier": in_tier,
        "xp_per_tier": EC.PASS_XP_PER_TIER,
        "is_premium": p.is_premium,
        "premium_price": EC.PREMIUM_PASS_PRICE_GEMS,
        "tiers": tiers,
    }


def buy_premium(db: Session, user_id: int, request_id=None, intended_season=None) -> dict:
    if not request_id or not intended_season:
        return {'ok': False, 'msg': 'معرف الشراء والموسم مطلوبان'}
    from app.domains.users.models import User
    p = get_or_create_pass(db, user_id)
    user = db.query(User).filter(User.id == user_id).populate_existing().with_for_update().first()
    if not user:
        return {"ok": False, "msg": "المستخدم غير موجود"}
    from app.domains.games.models import PremiumReceipt
    if request_id is not None:
        from uuid import UUID
        try:
            request_id = str(UUID(str(request_id)))
        except ValueError:
            return {"ok": False, "msg": "معرف طلب الشراء غير صالح"}
        existing = db.get(PremiumReceipt, (user_id, request_id))
        if existing:
            if intended_season != existing.season:
                return {"ok": False, "msg": "طلب الشراء مرتبط بموسم آخر"}
            return {"ok": True, "gems_left": existing.gems_left, "price": existing.price}
        if intended_season != p.season_key:
            return {"ok": False, "msg": "تغير الموسم. افتح البطاقة الجديدة قبل الشراء."}
    db.refresh(p, with_for_update=True)
    if p.is_premium:
        return {"ok": False, "msg": "لديك Premium بالفعل هذا الموسم"}
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        return {"ok": False, "msg": "المستخدم غير موجود"}
    price = EC.PREMIUM_PASS_PRICE_GEMS
    if (user.gems or 0) < price:
        return {"ok": False, "msg": f"تحتاج {price} جوهرة", "need": price,
                "have": user.gems or 0}
    user.gems -= price
    p.is_premium = True
    if request_id:
        db.add(PremiumReceipt(user_id=user_id, request_id=request_id, season=p.season_key,
                              gems_left=user.gems, price=price))
    db.commit()
    return {"ok": True, "gems_left": user.gems, "price": price}


def claim_tier(db: Session, user_id: int, tier: int, track: str, intended_season=None) -> dict:
    """يستلم جائزة محطة من مسار (free/premium). track=premium يتطلب is_premium."""
    from app.domains.users.models import User
    if track not in {"premium", "free"}:
        return {"ok": False, "msg": "مسار غير صالح"}
    if tier < 1 or tier > EC.PASS_TIERS:
        return {"ok": False, "msg": "محطة غير صالحة"}
    p = get_or_create_pass(db, user_id)
    user = db.query(User).filter(User.id == user_id).populate_existing().with_for_update().first()
    if not user:
        return {"ok": False, "msg": "المستخدم غير موجود"}
    db.refresh(p, with_for_update=True)
    if intended_season != p.season_key:
        return {'ok': False, 'msg': 'تغير الموسم. افتح البطاقة الحالية.'}
    if _tier_from_xp(p.pass_xp) < tier:
        return {"ok": False, "msg": "لم تبلغ هذه المحطة بعد"}
    if track == "premium" and not p.is_premium:
        return {"ok": False, "msg": "تحتاج Premium Pass"}

    field = "claimed_free" if track == "free" else "claimed_premium"
    claimed = set(json.loads(getattr(p, field) or "[]"))
    if tier in claimed:
        return {"ok": False, "msg": "استلمتها مسبقاً"}

    reward = (FREE_REWARDS if track == "free" else premium_rewards(p.season_key))[tier - 1]
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        return {"ok": False, "msg": "المستخدم غير موجود"}

    applied = {}
    if reward["type"] == "coins":
        user.coins = (user.coins or 0) + reward["amount"]; applied = {"coins": reward["amount"]}
    elif reward["type"] == "gems":
        user.gems = (user.gems or 0) + reward["amount"]; applied = {"gems": reward["amount"]}
    elif reward["type"] == "cosmetic":
        from sqlalchemy import text
        from app.domains.wallet.cosmetics import _init
        _init()
        db.execute(text("INSERT INTO player_cosmetics (user_id,item_id,category) VALUES (:uid,:item,'avatar') ON CONFLICT (user_id,item_id) DO NOTHING"),
                   {"uid": user_id, "item": reward["item_id"]})
        applied = {"cosmetic": reward["item_id"]}

    claimed.add(tier)
    setattr(p, field, json.dumps(sorted(claimed)))
    db.commit()
    return {"ok": True, "reward": applied, "track": track, "tier": tier}
