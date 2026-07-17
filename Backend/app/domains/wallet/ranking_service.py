"""
ranking_service.py — نظام التصنيف (Elo) الموسمي.

- Elo لكل لاعب/لعبة/موسم، مع هامش الفوز لحروف.
- soft reset تلقائي عند دخول موسم جديد (يُحسب من رتبة الموسم السابق).
- جواهر عند عبور مجموعة رتبة أعلى (مرة لكل موسم).
- كل الثوابت من economy_config.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.wallet import economy_config as EC
from app.domains.wallet.period_keys import season_key
from app.domains.wallet.progression_models import PlayerRank


def _tier_rank_index(tier_key: str) -> int:
    for i, t in enumerate(EC.RANK_TIERS):
        if t["key"] == tier_key:
            return i
    return 0


def _expected_score(elo_a: int, elo_b: int) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def _prev_season_elo(db: Session, user_id: int, game_mode: str, current_key: str):
    """أحدث Elo للاعب في هذه اللعبة من موسم سابق (لأجل soft reset)."""
    row = (db.query(PlayerRank)
             .filter(PlayerRank.user_id == user_id,
                     PlayerRank.game_mode == game_mode,
                     PlayerRank.season_key != current_key)
             .order_by(PlayerRank.updated_at.desc())
             .first())
    return row.elo if row else None


def _soft_reset(prev_elo: int) -> int:
    base = EC.SEASON_RESET_BASELINE
    reset = base + round((prev_elo - base) * EC.SEASON_SOFT_RESET_FACTOR)
    floor = EC.RANK_TIERS[0]["min_elo"]
    return max(floor, reset)


def get_or_create_rank(db: Session, user_id: int, game_mode: str) -> PlayerRank:
    """يجلب صف رتبة الموسم الحالي، ويطبّق soft reset من الموسم السابق إن جديد."""
    skey = season_key()
    rank = (db.query(PlayerRank)
              .filter(PlayerRank.user_id == user_id,
                      PlayerRank.game_mode == game_mode,
                      PlayerRank.season_key == skey)
              .first())
    if rank:
        return rank

    prev = _prev_season_elo(db, user_id, game_mode, skey)
    start_elo = _soft_reset(prev) if prev is not None else EC.ELO_STARTING
    start_tier = EC.tier_for_elo(start_elo)["key"]
    rank = PlayerRank(
        user_id=user_id, game_mode=game_mode, season_key=skey,
        elo=start_elo, peak_elo=start_elo, highest_tier=start_tier,
    )
    db.add(rank)
    db.flush()
    return rank


def apply_match(db: Session, winner_id: int, loser_id: int, game_mode: str,
                margin: str = "default") -> dict:
    """يحدّث Elo الطرفين بعد مباراة تنافسية. يرجع dict فيه جواهر العبور.

    margin: 'dominant' (2-0) | 'close' (2-1) | 'default'.
    """
    wr = get_or_create_rank(db, winner_id, game_mode)
    lr = get_or_create_rank(db, loser_id, game_mode)

    exp_w = _expected_score(wr.elo, lr.elo)
    mult = EC.ELO_MARGIN_MULT.get(margin, 1.0)
    k = EC.ELO_K_FACTOR * mult

    delta_w = round(k * (1.0 - exp_w))
    delta_l = round(k * (0.0 - (1.0 - exp_w)))

    # ⚔️ قسوة الخسارة المتصاعدة بالرتبة (Brawl Stars):
    # البرونزي يخسر نصف النقاط (صعود محمي)، النخبة تخسر 130% (كل مباراة تحسب)
    loser_tier = EC.tier_for_elo(lr.elo)["key"]
    severity = getattr(EC, "LOSS_SEVERITY_BY_TIER", {}).get(loser_tier, 1.0)
    delta_l = round(delta_l * severity)

    # 🚀 Rank Boost: أول مباريات الموسم مكاسبها مضاعفة (تسلّق متسارع
    # بعد الـreset + مباريات تموضع للمبتدئين)
    boost_n = getattr(EC, "RANK_BOOST_MATCHES", 0)
    boost_mult = getattr(EC, "RANK_BOOST_MULT", 1.0)
    if boost_n and wr.matches < boost_n:
        delta_w = round(delta_w * boost_mult)

    # 🧢 سقف التغيّر بالمباراة: ±(K الأساسي × 1.5) بعد كل المضاعفات
    cap = round(EC.ELO_K_FACTOR * getattr(EC, "ELO_DELTA_CAP_FACTOR", 1.5))
    delta_w = max(-cap, min(cap, delta_w))
    delta_l = max(-cap, min(cap, delta_l))

    gem_awards = {}

    for rank, delta, is_win in ((wr, delta_w, True), (lr, delta_l, False)):
        old_tier_idx = _tier_rank_index(EC.tier_for_elo(rank.elo)["key"])
        # 🛡️ حماية الأرضية بالرتب العليا: من بلغ بلاتيني/نخبة هذا الموسم
        # لا ينهار أكثر من 100 نقطة تحت أرضية رتبته العليا
        floor = EC.RANK_TIERS[0]["min_elo"]
        if rank.highest_tier in getattr(EC, "DEMOTION_SHIELD_TIERS", ()):
            tier_min = next((t["min_elo"] for t in EC.RANK_TIERS
                             if t["key"] == rank.highest_tier), floor)
            floor = max(floor, tier_min - 100)
        rank.elo = max(floor, rank.elo + delta)
        rank.matches += 1
        if is_win:
            rank.wins += 1
        else:
            rank.losses += 1
        if rank.elo > rank.peak_elo:
            rank.peak_elo = rank.elo

        # جواهر العبور: بلوغ مجموعة أعلى من أعلى مجموعة بُلغت هذا الموسم
        new_tier = EC.tier_for_elo(rank.elo)
        highest_idx = _tier_rank_index(rank.highest_tier)
        new_idx = _tier_rank_index(new_tier["key"])
        if new_idx > highest_idx:
            rank.highest_tier = new_tier["key"]
            gems = EC.GEMS_PER_TIER_PROMOTION.get(new_tier["key"], 0)
            if gems > 0:
                gem_awards[rank.user_id] = {
                    "gems": gems, "tier": new_tier["key"],
                    "tier_name": new_tier["name"],
                }

    return {
        "winner_delta": delta_w, "loser_delta": delta_l,
        "winner_elo": wr.elo, "loser_elo": lr.elo,
        "gem_awards": gem_awards,
    }


def get_rank_snapshot(db: Session, user_id: int, game_mode: str) -> dict:
    rank = get_or_create_rank(db, user_id, game_mode)
    snap = EC.rank_snapshot(rank.elo)
    snap.update({
        "matches": rank.matches, "wins": rank.wins, "losses": rank.losses,
        "peak_elo": rank.peak_elo, "game_mode": game_mode,
    })
    return snap


def get_all_ranks(db: Session, user_id: int) -> dict:
    """رتب اللاعب في كل الألعاب للموسم الحالي (للبروفايل)."""
    skey = season_key()
    rows = (db.query(PlayerRank)
              .filter(PlayerRank.user_id == user_id,
                      PlayerRank.season_key == skey)
              .all())
    out = {}
    for r in rows:
        snap = EC.rank_snapshot(r.elo)
        snap.update({"matches": r.matches, "wins": r.wins, "losses": r.losses})
        out[r.game_mode] = snap
    return out
