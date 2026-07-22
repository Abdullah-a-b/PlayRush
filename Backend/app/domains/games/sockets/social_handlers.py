"""
معالجات اجتماعية داخل اللعب (مشتركة لكل الألعاب): طلب/حذف صداقة، حظر/رفع حظر،
والرد على طلب الصداقة. كانت موجودة في huroof فقط فتضيع في باقي الألعاب — الآن
تُسجَّل مرة واحدة عبر register_social_handlers(sio, get_room_state) في كل لعبة.

الأحداث تُحوَّل للـ worker مالك الغرفة (cluster._FWD_EVENTS)، لذا يعمل تحديد الخصم
عبر الغرفة مع تعدّد الـ workers. وكطبقة أمان إضافية نقبل target_id من الواجهة كبديل.
"""


async def _resolve_target(sio, sid, data, error_event, get_room_state):
    """يرجّع (user, target_sid, target_id) أو (None, None, None) بعد إرسال رسالة خطأ.
    يحدّد الخصم من الغرفة إن توفّرت على هذا الـ worker، وإلا من target_id المرسل."""
    from app.sockets.auth_helper import verify_socket_token
    user, db = verify_socket_token((data or {}).get('token'))
    if not user:
        await sio.emit(error_event, {'ok': False, 'msg': 'يجب تسجيل الدخول'}, to=sid)
        return None, None, None
    db.close()

    target_sid = None
    target_id = None
    room = get_room_state((data or {}).get('roomCode'))
    if room:
        target = next((p for p in room['players'] if p['sid'] != sid), None)
        if target:
            target_sid = target['sid']
            target_id = target.get('user_id') or (room.get('user_ids') or {}).get(target['sid'])

    # بديل: هوية الخصم من الواجهة (تعمل عبر أي worker)
    if not target_id and (data or {}).get('target_id') is not None:
        try:
            target_id = int(data['target_id'])
        except (TypeError, ValueError):
            target_id = None

    if not target_id:
        await sio.emit(error_event, {'ok': False, 'msg': 'تعذّر تحديد الخصم'}, to=sid)
        return None, None, None

    return user, target_sid, target_id


def register_social_handlers(sio, get_room_state):

    @sio.event
    async def friend_request_opponent(sid, data):
        """طلب صداقة للخصم. data: { roomCode, token, target_id? }"""
        user, target_sid, target_id = await _resolve_target(sio, sid, data, 'friend_result', get_room_state)
        if not user:
            return
        from app.domains.users.friends import send_friend_request
        result = send_friend_request(user.id, target_id)
        await sio.emit('friend_result', result, to=sid)

        if result.get('ok'):
            from app.domains.notifications.service import add_notification, find_online_sid
            notif = add_notification(
                target_id, 'friend_request',
                f'أرسل لك {user.player_name} طلب صداقة',
                sender_id=user.id
            )
            online_sid = find_online_sid(target_id)
            if online_sid and notif:
                await sio.emit('new_notification', notif, to=online_sid)
            # toast لحظي داخل المباراة للخصم (لو معروف sid الخصم في هذه الغرفة)
            if target_sid:
                await sio.emit('ingame_friend_request', {
                    'requesterId': user.id,
                    'requesterName': user.player_name,
                }, to=target_sid)

    @sio.event
    async def remove_friend_opponent(sid, data):
        """حذف الخصم من الأصدقاء. data: { roomCode, token, target_id? }"""
        user, target_sid, target_id = await _resolve_target(sio, sid, data, 'friend_result', get_room_state)
        if not user:
            return
        from app.domains.users.friends import remove_friend
        result = remove_friend(user.id, target_id)
        await sio.emit('friend_result', result, to=sid)
        if result.get('ok') and target_sid:
            await sio.emit('opponent_unfriended', {}, to=target_sid)

    @sio.event
    async def block_opponent(sid, data):
        """حظر الخصم. data: { roomCode, token, target_id? }"""
        user, target_sid, target_id = await _resolve_target(sio, sid, data, 'block_result', get_room_state)
        if not user:
            return
        from app.domains.users.friends import block_user
        result = block_user(user.id, target_id)
        await sio.emit('block_result', result, to=sid)

    @sio.event
    async def unblock_opponent(sid, data):
        """رفع الحظر عن الخصم. data: { roomCode, token, target_id? }"""
        user, target_sid, target_id = await _resolve_target(sio, sid, data, 'unblock_result', get_room_state)
        if not user:
            return
        from app.domains.users.friends import unblock_user
        result = unblock_user(user.id, target_id)
        await sio.emit('unblock_result', result, to=sid)
