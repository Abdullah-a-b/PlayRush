"""هوية اللاعب المنطقية ثابتة عند تبديل اتصال Socket.IO."""
def resolve_sid(room, sid):
    aliases = room.get('sid_aliases', {}) if room else {}
    visited = set()
    while sid in aliases and sid not in visited:
        visited.add(sid)
        sid = aliases[sid]
    return sid


def remap_match_sid(room, old_sid, new_sid):
    if not old_sid or old_sid == new_sid:
        return
    room.setdefault('sid_aliases', {})[old_sid] = new_sid
    gs = room.get('game_state')
    if gs is None:
        return
    for attr, value in vars(gs).items():
        if isinstance(value, dict) and old_sid in value:
            value[new_sid] = value.pop(old_sid)
        elif attr in {'p1','p2','turn','buzzed_player','winner','first_turn_round'} and value == old_sid:
            setattr(gs, attr, new_sid)
    for player in getattr(gs, 'players', []):
        if player.get('sid') == old_sid:
            player['sid'] = new_sid
    if room.get('host') == old_sid:
        room['host'] = new_sid
    if old_sid in room.get('user_ids', {}):
        room['user_ids'][new_sid] = room['user_ids'].pop(old_sid)
