"""
leaderboard_service.py — الصدارة بقسمين.

القسم 1 (Ranked): ترتيب حسب Elo الموسمي لكل لعبة.
القسم 2 (Wins): ترتيب حسب عدد الانتصارات، وعند التعادل الأقل مباريات
                يتقدّم (كفاءة أعلى — قرار المطوّر).
صدارة عامة (categories): متوسط Elo عبر الألعاب لمن لعب ≥3 ألعاب.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.wallet import economy_config as EC
from app.domains.wallet.period_keys import season_key
from app.domains.wallet.progression_models import PlayerRank
from app.domains.users.models import User


def _row(user, extra):
    base = {
        "user_id": user.id, "player_name": user.player_name or "لاعب",
        "avatar": user.avatar, "player_id": user.player_id,
    }
    base.update(extra)
    return base


def ranked_board(db: Session, game_mode: str, limit: int = 50) -> list:
    """أعلى اللاعبين بالـElo في لعبة (الموسم الحالي)."""
    skey = season_key()
    rows = (db.query(PlayerRank, User)
              .join(User, User.id == PlayerRank.user_id)
              .filter(PlayerRank.game_mode == game_mode,
                      PlayerRank.season_key == skey,
                      PlayerRank.matches > 0)
              .order_by(PlayerRank.elo.desc())
              .limit(limit).all())
    out = []
    for i, (rank, user) in enumerate(rows, 1):
        snap = EC.rank_snapshot(rank.elo)
        out.append(_row(user, {
            "position": i, "elo": rank.elo, "rank_label": snap["label"],
            "division_progress": snap.get("division_progress", 0),
            "tier": snap["tier"], "color": snap["color"],
            "wins": rank.wins, "losses": rank.losses, "matches": rank.matches,
        }))
    return out


def wins_board(db: Session, game_mode: str, limit: int = 50) -> list:
    """أعلى اللاعبين بالانتصارات؛ التعادل يُحسم بالأقل مباريات (كفاءة)."""
    skey = season_key()
    rows = (db.query(PlayerRank, User)
              .join(User, User.id == PlayerRank.user_id)
              .filter(PlayerRank.game_mode == game_mode,
                      PlayerRank.season_key == skey,
                      PlayerRank.wins > 0)
              .order_by(PlayerRank.wins.desc(), PlayerRank.matches.asc())
              .limit(limit).all())
    out = []
    for i, (rank, user) in enumerate(rows, 1):
        out.append(_row(user, {
            "position": i, "wins": rank.wins, "losses": rank.losses,
            "matches": rank.matches,
            "win_rate": round(rank.wins / rank.matches * 100) if rank.matches else 0,
        }))
    return out


def global_board(db: Session, limit: int = 50, min_games: int = 3) -> list:
    """صدارة عامة (categories): متوسط Elo لمن لعب ≥min_games ألعاب مختلفة.

    يحمي «نخبة المنصة» للاعبين متعددي الألعاب (قرار الوثيقة).
    """
    skey = season_key()
    agg = (db.query(
                PlayerRank.user_id,
                func.avg(PlayerRank.elo).label("avg_elo"),
                func.count(PlayerRank.game_mode).label("games"),
                func.sum(PlayerRank.wins).label("total_wins"),
                func.sum(PlayerRank.matches).label("total_matches"))
             .filter(PlayerRank.season_key == skey, PlayerRank.matches > 0)
             .group_by(PlayerRank.user_id)
             .having(func.count(PlayerRank.game_mode) >= min_games)
             .subquery())

    rows = (db.query(agg, User)
              .join(User, User.id == agg.c.user_id)
              .order_by(agg.c.avg_elo.desc())
              .limit(limit).all())
    out = []
    for i, row in enumerate(rows, 1):
        user = row.User
        avg_elo = int(row.avg_elo)
        snap = EC.rank_snapshot(avg_elo)
        out.append(_row(user, {
            "position": i, "avg_elo": avg_elo, "rank_label": snap["label"],
            "tier": snap["tier"], "color": snap["color"],
            "games": int(row.games), "total_wins": int(row.total_wins or 0),
            "total_matches": int(row.total_matches or 0),
        }))
    return out


def my_position(db: Session, user_id: int, game_mode: str) -> dict:
    """موقع اللاعب في الصدارة (لعرضه إن كان خارج الأعلى-50)."""
    skey = season_key()
    my = (db.query(PlayerRank)
            .filter(PlayerRank.user_id == user_id,
                    PlayerRank.game_mode == game_mode,
                    PlayerRank.season_key == skey)
            .first())
    if not my or my.matches == 0:
        return {"ranked": False}
    higher = (db.query(func.count(PlayerRank.id))
                .filter(PlayerRank.game_mode == game_mode,
                        PlayerRank.season_key == skey,
                        PlayerRank.matches > 0,
                        PlayerRank.elo > my.elo)
                .scalar())
    snap = EC.rank_snapshot(my.elo)
    return {"ranked": True, "position": (higher or 0) + 1,
            "elo": my.elo, "rank_label": snap["label"], "tier": snap["tier"]}
