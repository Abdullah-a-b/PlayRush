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
        elif tier % 10 == 0:
            premium.append({"type": "cosmetic", "amount": 1, "icon": "🎨",
                            "note": "تجميل حصري"})
        elif tier % 5 == 0:
            premium.append({"type": "coins", "amount": 250, "icon": "🪙"})
        else:
            premium.append({"type": "coins", "amount": 120, "icon": "🪙"})
    return free, premium


FREE_REWARDS, PREMIUM_REWARDS = _build_pass_rewards()


def get_or_create_pass(db: Session, user_id: int) -> PlayerPass:
    skey = season_key()
    p = (db.query(PlayerPass)
           .filter(PlayerPass.user_id == user_id, PlayerPass.season_key == skey)
           .first())
    if not p:
        p = PlayerPass(user_id=user_id, season_key=skey, pass_xp=0,
                       is_premium=False, claimed_free="[]", claimed_premium="[]")
        db.add(p)
        db.commit()
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
    db.commit()
    return {"added": amount, "pass_xp": p.pass_xp,
            "tier_before": before, "tier_after": after,
            "tiers_gained": after - before}


def get_pass_state(db: Session, user_id: int) -> dict:
    p = get_or_create_pass(db, user_id)
    tier = _tier_from_xp(p.pass_xp)
    in_tier = p.pass_xp - tier * EC.PASS_XP_PER_TIER
    claimed_free = set(json.loads(p.claimed_free or "[]"))
    claimed_premium = set(json.loads(p.claimed_premium or "[]"))

    tiers = []
    for i in range(1, EC.PASS_TIERS + 1):
        tiers.append({
            "tier": i,
            "unlocked": i <= tier,
            "free": FREE_REWARDS[i - 1],
            "free_claimed": i in claimed_free,
            "premium": PREMIUM_REWARDS[i - 1],
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


def buy_premium(db: Session, user_id: int) -> dict:
    from app.domains.users.models import User
    p = get_or_create_pass(db, user_id)
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
    db.commit()
    return {"ok": True, "gems_left": user.gems, "price": price}


def claim_tier(db: Session, user_id: int, tier: int, track: str) -> dict:
    """يستلم جائزة محطة من مسار (free/premium). track=premium يتطلب is_premium."""
    from app.domains.users.models import User
    if tier < 1 or tier > EC.PASS_TIERS:
        return {"ok": False, "msg": "محطة غير صالحة"}
    p = get_or_create_pass(db, user_id)
    if _tier_from_xp(p.pass_xp) < tier:
        return {"ok": False, "msg": "لم تبلغ هذه المحطة بعد"}
    if track == "premium" and not p.is_premium:
        return {"ok": False, "msg": "تحتاج Premium Pass"}

    field = "claimed_free" if track == "free" else "claimed_premium"
    claimed = set(json.loads(getattr(p, field) or "[]"))
    if tier in claimed:
        return {"ok": False, "msg": "استلمتها مسبقاً"}

    reward = (FREE_REWARDS if track == "free" else PREMIUM_REWARDS)[tier - 1]
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        return {"ok": False, "msg": "المستخدم غير موجود"}

    applied = {}
    if reward["type"] == "coins":
        user.coins = (user.coins or 0) + reward["amount"]; applied = {"coins": reward["amount"]}
    elif reward["type"] == "gems":
        user.gems = (user.gems or 0) + reward["amount"]; applied = {"gems": reward["amount"]}
    elif reward["type"] == "cosmetic":
        applied = {"cosmetic": reward.get("note", "تجميل")}
        # منح التجميل الحصري يُدار عبر نظام cosmetics عند ربطه بمحتوى فعلي

    claimed.add(tier)
    setattr(p, field, json.dumps(sorted(claimed)))
    db.commit()
    return {"ok": True, "reward": applied, "track": track, "tier": tier}
