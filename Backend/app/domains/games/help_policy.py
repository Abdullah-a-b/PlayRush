"""تجهيز مساعدات المباراة وشروط التأثير قبل خصم المخزون."""
import importlib


def load_match_loadout(room, gs, sid, game):
    snapshots = getattr(gs, 'match_help_loadouts', None)
    if snapshots is None:
        gs.match_help_loadouts = snapshots = {}
    if sid in snapshots:
        return snapshots[sid]
    if game == 'career' and getattr(gs, 'is_solo', False):
        from app.domains.games.career.solo_bot import BOT_SID
        if sid == BOT_SID:
            snapshots[sid] = list(gs.bot_loadout)
            return snapshots[sid]
    catalog = importlib.import_module('app.domains.games.' + game + '.helps')
    player = next((p for p in room.get('players', []) if p.get('sid') == sid), None)
    uid = (player or {}).get('user_id') or (room.get('user_ids') or {}).get(sid)
    if not uid:
        # التدريب كزائر يتبع التجهيز الأساسي نفسه، لا كتالوجًا مفتوحًا.
        if getattr(gs, 'is_solo', False):
            snapshots[sid] = list(catalog.DEFAULT_LOADOUT)
            return snapshots[sid]
        return []
    from app.infrastructure.database import SessionLocal
    from app.domains.users.models import User
    from app.domains.wallet.loadout import get_loadout_for_game
    from app.domains.wallet.cosmetics import owns_cosmetic
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if not user or user.is_banned:
            return []
        level = user.level or 0
        fourth = level >= catalog.FOURTH_SLOT_LEVEL and owns_cosmetic(uid, catalog.FOURTH_SLOT_ITEM)
        limit = catalog.get_slots_for_player(level, fourth)
        saved = get_loadout_for_game(uid, game, catalog.DEFAULT_LOADOUT)
        saved = saved if isinstance(saved, list) else list(catalog.DEFAULT_LOADOUT)
        clean = list(dict.fromkeys(x for x in saved if isinstance(x, str) and catalog.is_valid_help(x)
                     and level >= (catalog.get_help(x) or {}).get('unlock_level', 0)))[:limit]
        if getattr(catalog, 'loadout_conflict', lambda x:None)(clean):
            clean = list(catalog.DEFAULT_LOADOUT)[:limit]
        snapshots[sid] = clean
        return clean
    finally:
        db.close()


def freeze_match_loadouts(room):
    import uuid
    match_id = room.setdefault('settlement_id', uuid.uuid4().hex)
    for player in room.get('players', []):
        player['match_id'] = match_id
    gs = room.get('game_state')
    if gs:
        for p in room.get('players', []):
            if p.get('sid'):
                load_match_loadout(room, gs, p['sid'], room.get('game_mode', 'huroof'))


def help_denial(room, gs, sid, game, help_id):
    catalog = importlib.import_module('app.domains.games.' + game + '.helps')
    if not catalog.is_valid_help(help_id):
        return 'المساعدة غير متاحة'
    import time
    if (catalog.get_help(help_id) or {}).get('timing') == 'buzzed' and getattr(gs, 'answer_deadline', 0) <= time.time():
        return 'انتهت نافذة الإجابة'
    if help_id not in load_match_loadout(room, gs, sid, game):
        return 'هذه المساعدة ليست ضمن تجهيزك لهذه المباراة'
    if game == 'career':
        current = gs.current_player or {}
        field = {'c_nationality':'nationality', 'c_era':'era', 'c_position':'position'}.get(help_id)
        if field and not current.get(field):
            return 'لا تتوفر معلومة لهذه الشخصية؛ لم يُخصم شيء'
    elif game == 'whoami':
        current = gs.current or {}
        field = {'w_reveal_category':'category','w_reveal_era':'era'}.get(help_id)
        if field and not current.get(field):
            return 'المعلومة غير متاحة؛ لم يُخصم شيء'
    elif game == 'knowledge':
        if help_id in {'k_first_letter','k_last_letter','k_letter_count','k_hawk_eye'} and gs.pool_exhausted():
            return 'القائمة نفدت؛ لم يُخصم شيء'
    elif game == 'huroof':
        timer = getattr(gs, 'active_timer', None)
        import time
        if help_id in {'extend_time','freeze_timer'} and (not timer or timer.get('version') != gs.state_version or timer.get('ends_at', 0) <= time.time()):
            return 'لا يوجد مؤقت نشط الآن'
        if help_id == 'change_question' and (gs.stage not in ('buzz_r1','question') or not gs.active_hex):
            return 'لا يمكن تغيير السؤال الآن'
        if help_id == 'skip_letter' and (gs.stage not in ('buzz_r1','question') or not gs.active_hex):
            return 'لا يمكن التخطي الآن'
        answer = (gs.current_question or {}).get('answer', '')
        if help_id == 'reveal_second_letter' and len(answer.replace(' ', '')) < 2:
            return 'الإجابة قصيرة جدًا؛ لم يُخصم شيء'
    return None
