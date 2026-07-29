""" معالجات المتجر"""
from app.sockets.auth_helper import verify_socket_token
from app.domains.wallet.store_catalog import (get_store_for_lobby, get_store_for_categories,
                                         find_item, get_base_owned_cosmetics)


def _owns_fourth_slot(user_id):
    from app.domains.wallet.cosmetics import owns_cosmetic
    from app.domains.games.huroof.helps import FOURTH_SLOT_ITEM
    return owns_cosmetic(user_id, FOURTH_SLOT_ITEM)


def _solo_virtual_inventory(inventory, catalog, room_code):
    """🤖 مخزون افتراضي داخل الغرف الفردية.

    السولو تدريب: المساعدات لا تُخصم فيه (انظر *_use_help في كل لعبة)،
    ومن ثمّ لا معنى لأن يمنعك رصيدٌ فارغ من تجربة مساعدة. نرفع كل مساعدة
    مفعّلة إلى 1 على الأقل **في الرسالة المُرسلة للواجهة فقط**.

    ⚠️ لا نضيف شيئاً لقاعدة البيانات عمداً: لو منحنا مساعدة حقيقية عند كل
    دخول سولو لصارت مزرعة مجانية تُستهلك في الأونلاين. والرصيد الحقيقي
    يبقى كما هو — الترقيع يرفع الصفر ولا يخفض ما فوقه.

    ولا نثق بأي علم "solo" قادم من العميل: نتحقق من حالة الغرفة نفسها.
    """
    if not room_code:
        return inventory
    try:
        from app.domains.games.core_manager import get_room_state
        room = get_room_state(room_code)
        gs = (room or {}).get('game_state')
        if not gs or not getattr(gs, 'is_solo', False):
            return inventory
    except Exception:
        return inventory

    inv = dict(inventory or {})
    for h in (catalog or []):
        hid = h.get('id') if isinstance(h, dict) else None
        if hid and int(inv.get(hid, 0)) < 1:
            inv[hid] = 1
    return inv


def register_store_events(sio):

    @sio.on('clear_equipped')
    async def clear_equipped(sid, data):
        """يلغي تجهيز نوع (مثل الثيم  الافتراضي). data: { token, slotType }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            slot_type = (data or {}).get('slotType')
            if slot_type in ('theme', 'avatar'):
                from app.domains.wallet.equipped import set_equipped
                set_equipped(user.id, slot_type, None)
            await sio.emit('equip_result', {'ok': True, 'msg': 'تم الإلغاء', 'category': slot_type, 'cleared': True}, to=sid)
        finally:
            db.close()

    @sio.on('get_owned_avatars')
    async def get_owned_avatars(sid, data):
        """يُرجع ملفات الأفاتار التي يملكها اللاعب (للإعدادات)."""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            from app.domains.wallet.cosmetics import get_owned_cosmetics
            from app.domains.wallet.store_catalog import COSMETICS
            owned_ids = get_owned_cosmetics(user.id)
            files = []
            for c in COSMETICS:
                if c.get('category') == 'avatar' and c['id'] in owned_ids and c.get('asset'):
                    files.append(c['asset'].split('/')[-1])
            await sio.emit('owned_avatars_data', {'files': files}, to=sid)
        finally:
            db.close()

    @sio.on('get_owned_themes')
    async def get_owned_themes(sid, data):
        """يُرجع الثيمات المملوكة + المُجهّز حالياً (للإعدادات)."""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            from app.domains.wallet.cosmetics import get_owned_cosmetics
            from app.domains.wallet.store_catalog import COSMETICS
            from app.domains.wallet.equipped import get_equipped
            owned_ids = get_owned_cosmetics(user.id)
            themes = []
            for c in COSMETICS:
                if c.get('category') == 'theme' and c['id'] in owned_ids:
                    themes.append({'id': c['id'], 'name': c['name'], 'icon': c.get('icon', '🎨')})
            equipped = get_equipped(user.id)
            await sio.emit('owned_themes_data', {
                'themes': themes, 'equipped': equipped.get('theme'),
            }, to=sid)
        finally:
            db.close()

    @sio.on('fetch_store')
    async def fetch_store(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            context = (data or {}).get('context') or 'categories'
            store = get_store_for_categories() if context == 'categories' else get_store_for_lobby(context)
            from app.domains.wallet.help_inventory import get_inventory, grant_starter_helps_once
            from app.domains.wallet.cosmetics import get_owned_cosmetics
            from app.domains.wallet.equipped import get_equipped
            grant_starter_helps_once(user.id)
            help_inv = get_inventory(user.id)
            owned_cosmetics = list(set(get_owned_cosmetics(user.id) + get_base_owned_cosmetics()))
            await sio.emit('store_data', {
                'context': context, 'helps': store['helps'],
                'upgrades': store.get('upgrades', []), 'cosmetics': store['cosmetics'],
                'wallet': {'coins': user.coins or 0, 'gems': user.gems or 0},
                'level': user.level or 0, 'help_inventory': help_inv,
                'owned_cosmetics': owned_cosmetics, 'equipped': get_equipped(user.id),
            }, to=sid)
        finally:
            db.close()

    @sio.on('purchase_item')
    async def purchase_item(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            item = find_item((data or {}).get('itemId'))
            if not item:
                await sio.emit('purchase_result', {'ok': False, 'msg': 'العنصر غير موجود'}, to=sid); return
            if (user.level or 0) < item['unlock_level']:
                await sio.emit('purchase_result', {'ok': False, 'msg': f"يُفتح في المستوى {item['unlock_level']}"}, to=sid); return
            from app.domains.wallet.cosmetics import owns_cosmetic, grant_cosmetic
            if item['category'] != 'help':
                if item['id'] in get_base_owned_cosmetics() or owns_cosmetic(user.id, item['id']):
                    await sio.emit('purchase_result', {'ok': False, 'msg': 'تملك هذا العنصر مسبقاً'}, to=sid); return
            price = item['price']; currency = item['currency']
            balance = (user.coins or 0) if currency == 'coins' else (user.gems or 0)
            if balance < price:
                cur = 'كوينز' if currency == 'coins' else 'جوهر'
                await sio.emit('purchase_result', {'ok': False, 'msg': f'رصيدك من الـ{cur} غير كافٍ'}, to=sid); return
            from sqlalchemy import text
            from app.infrastructure.database import engine
            col = 'coins' if currency == 'coins' else 'gems'
            with engine.connect() as conn:
                res = conn.execute(text(f"UPDATE users SET {col} = {col} - :p WHERE id = :u AND {col} >= :p"),
                                   {"p": price, "u": user.id})
                conn.commit()
                if res.rowcount == 0:
                    await sio.emit('purchase_result', {'ok': False, 'msg': 'فشل الخصم'}, to=sid); return
            if item['category'] == 'help':
                from app.domains.wallet.help_inventory import add_help
                add_help(user.id, item['ref_id'], 1)
            else:
                grant_cosmetic(user.id, item['id'], item['category'])
            nb = balance - price
            await sio.emit('purchase_result', {
                'ok': True, 'msg': f"تم شراء {item['name']} ✅", 'itemId': item['id'],
                'category': item['category'], 'asset': item.get('asset'),
                'wallet': {'coins': (nb if currency == 'coins' else (user.coins or 0)),
                           'gems': (nb if currency == 'gems' else (user.gems or 0))},
            }, to=sid)
        finally:
            db.close()

    @sio.on('get_help_loadout')
    async def get_help_loadout(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            from app.domains.wallet.loadout import get_loadout
            from app.domains.wallet.help_inventory import get_inventory
            # المساعدات خاصة بكل لعبة — نحدّد اللعبة من الطلب (افتراضياً حروف)
            game = (data or {}).get('game') or 'huroof'
            # تُرسله شاشة اللعبة كي نتعرّف على الغرفة الفردية (اختياري)
            _room_code = (data or {}).get('roomCode')
            level = user.level or 0
            owns_fourth = _owns_fourth_slot(user.id)
            if game == 'huroof':
                from app.domains.games.huroof.helps import (get_enabled_catalog, get_slots_for_player,
                                                     FOURTH_SLOT_LEVEL, DEFAULT_LOADOUT)
                await sio.emit('help_loadout_data', {
                    'game': game,
                    'loadout': get_loadout(user.id, level),
                    'inventory': _solo_virtual_inventory(get_inventory(user.id), get_enabled_catalog(), _room_code),
                    'catalog': get_enabled_catalog(), 'slots': get_slots_for_player(level, owns_fourth),
                    'ownsFourth': owns_fourth, 'fourthSlotLevel': FOURTH_SLOT_LEVEL,
                    'level': level, 'defaultLoadout': DEFAULT_LOADOUT,
                }, to=sid)
            elif game == 'career':
                from app.domains.games.career.helps import (get_enabled_catalog as c_catalog,
                    get_slots_for_player as c_slots, FOURTH_SLOT_LEVEL as C_FSL,
                    FOURTH_SLOT_ITEM as C_FSI, DEFAULT_LOADOUT as C_DEFAULTS)
                from app.domains.wallet.help_inventory import grant_career_starter
                from app.domains.wallet.loadout import get_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                from app.domains.games.core_manager import _allow_same_ip
                grant_career_starter(user.id)  # هدية أول مرة: 3 عادية ×1
                owns4 = owns_cosmetic(user.id, C_FSI)
                await sio.emit('help_loadout_data', {
                    'game': game,
                    'loadout': get_loadout_for_game(user.id, 'career', C_DEFAULTS),
                    'inventory': _solo_virtual_inventory(get_inventory(user.id), c_catalog(), _room_code),
                    'catalog': c_catalog(), 'slots': c_slots(level, owns4),
                    'ownsFourth': owns4, 'fourthSlotLevel': C_FSL,
                    'level': level, 'defaultLoadout': C_DEFAULTS,
                    'devMode': _allow_same_ip(),
                }, to=sid)
            elif game == 'bank':
                from app.domains.games.bank.helps import (get_enabled_catalog as b_catalog,
                    get_slots_for_player as b_slots, FOURTH_SLOT_LEVEL as B_FSL,
                    FOURTH_SLOT_ITEM as B_FSI, DEFAULT_LOADOUT as B_DEFAULTS,
                    CONFLICTS as B_CONFLICTS)
                from app.domains.wallet.help_inventory import grant_bank_starter
                from app.domains.wallet.loadout import get_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                from app.domains.games.core_manager import _allow_same_ip
                grant_bank_starter(user.id)  # هدية أول مرة: 3 عادية ×1
                owns4b = owns_cosmetic(user.id, B_FSI)
                await sio.emit('help_loadout_data', {
                    'game': game,
                    'loadout': get_loadout_for_game(user.id, 'bank', B_DEFAULTS),
                    'inventory': _solo_virtual_inventory(get_inventory(user.id), b_catalog(), _room_code),
                    'catalog': b_catalog(), 'slots': b_slots(level, owns4b),
                    'ownsFourth': owns4b, 'fourthSlotLevel': B_FSL,
                    'conflicts': B_CONFLICTS,
                    'level': level, 'defaultLoadout': B_DEFAULTS,
                    'devMode': _allow_same_ip(),
                }, to=sid)
            elif game == 'knowledge':
                from app.domains.games.knowledge.helps import (get_enabled_catalog as k_catalog,
                    get_slots_for_player as k_slots, FOURTH_SLOT_LEVEL as K_FSL,
                    FOURTH_SLOT_ITEM as K_FSI, DEFAULT_LOADOUT as K_DEFAULTS,
                    CONFLICTS as K_CONFLICTS)
                from app.domains.wallet.help_inventory import grant_knowledge_starter
                from app.domains.wallet.loadout import get_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                from app.domains.games.core_manager import _allow_same_ip
                grant_knowledge_starter(user.id)  # هدية أول مرة: الأساسية ×1
                owns4k = owns_cosmetic(user.id, K_FSI)
                await sio.emit('help_loadout_data', {
                    'game': game,
                    'loadout': get_loadout_for_game(user.id, 'knowledge', K_DEFAULTS),
                    'inventory': _solo_virtual_inventory(get_inventory(user.id), k_catalog(), _room_code),
                    'catalog': k_catalog(), 'slots': k_slots(level, owns4k),
                    'ownsFourth': owns4k, 'fourthSlotLevel': K_FSL,
                    'conflicts': K_CONFLICTS,
                    'level': level, 'defaultLoadout': K_DEFAULTS,
                    'devMode': _allow_same_ip(),
                }, to=sid)
            elif game == 'whoami':
                from app.domains.games.whoami.helps import (get_enabled_catalog as w_catalog,
                    get_slots_for_player as w_slots, FOURTH_SLOT_LEVEL as W_FSL,
                    FOURTH_SLOT_ITEM as W_FSI, DEFAULT_LOADOUT as W_DEFAULTS,
                    CONFLICTS as W_CONFLICTS)
                from app.domains.wallet.help_inventory import grant_whoami_starter
                from app.domains.wallet.loadout import get_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                from app.domains.games.core_manager import _allow_same_ip
                grant_whoami_starter(user.id)  # هدية أول مرة: الأساسية ×1
                owns4w = owns_cosmetic(user.id, W_FSI)
                await sio.emit('help_loadout_data', {
                    'game': game,
                    'loadout': get_loadout_for_game(user.id, 'whoami', W_DEFAULTS),
                    'inventory': _solo_virtual_inventory(get_inventory(user.id), w_catalog(), _room_code),
                    'catalog': w_catalog(), 'slots': w_slots(level, owns4w),
                    'ownsFourth': owns4w, 'fourthSlotLevel': W_FSL,
                    'conflicts': W_CONFLICTS,
                    'level': level, 'defaultLoadout': W_DEFAULTS,
                    'devMode': _allow_same_ip(),
                }, to=sid)
            else:
                # ألعاب أخرى: لا مساعدات بعد (كتالوج فارغ)
                await sio.emit('help_loadout_data', {
                    'game': game,
                    'loadout': [], 'inventory': get_inventory(user.id),
                    'catalog': [], 'slots': 3,
                    'ownsFourth': False, 'fourthSlotLevel': 99,
                    'level': level, 'defaultLoadout': [],
                }, to=sid)
        finally:
            db.close()

    @sio.on('set_help_loadout')
    async def set_help_loadout(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            from app.domains.wallet.help_inventory import get_inventory
            game = (data or {}).get('game') or 'huroof'
            slots = (data or {}).get('slots') or []
            inv = get_inventory(user.id)
            if game == 'career':
                from app.domains.games.career.helps import (get_slots_for_player as c_slots,
                    DEFAULT_LOADOUT as C_DEFAULTS, is_valid_help as c_valid,
                    FOURTH_SLOT_ITEM as C_FSI)
                from app.domains.wallet.loadout import set_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                for s in slots:
                    if s not in inv and s not in C_DEFAULTS:
                        await sio.emit('help_loadout_result', {'ok': False, 'msg': 'لا تملك إحدى المساعدات'}, to=sid); return
                max_slots = c_slots(user.level or 0, owns_cosmetic(user.id, C_FSI))
                await sio.emit('help_loadout_result',
                    set_loadout_for_game(user.id, 'career', slots, max_slots, c_valid), to=sid)
                return
            if game == 'bank':
                from app.domains.games.bank.helps import (get_slots_for_player as b_slots,
                    DEFAULT_LOADOUT as B_DEFAULTS, is_valid_help as b_valid,
                    FOURTH_SLOT_ITEM as B_FSI, loadout_conflict, get_help as b_get)
                from app.domains.wallet.loadout import set_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                for s in slots:
                    if s not in inv and s not in B_DEFAULTS:
                        await sio.emit('help_loadout_result', {'ok': False, 'msg': 'لا تملك إحدى المساعدات'}, to=sid); return
                # تعارض: درع الرصيد × فرصة ثانية
                conf = loadout_conflict(slots)
                if conf:
                    n1 = (b_get(conf[0]) or {}).get('name', conf[0])
                    n2 = (b_get(conf[1]) or {}).get('name', conf[1])
                    await sio.emit('help_loadout_result',
                        {'ok': False, 'msg': f'لا يمكن تجهيز "{n1}" مع "{n2}" معاً'}, to=sid)
                    return
                max_slots = b_slots(user.level or 0, owns_cosmetic(user.id, B_FSI))
                await sio.emit('help_loadout_result',
                    set_loadout_for_game(user.id, 'bank', slots, max_slots, b_valid), to=sid)
                return
            if game == 'knowledge':
                from app.domains.games.knowledge.helps import (get_slots_for_player as k_slots,
                    DEFAULT_LOADOUT as K_DEFAULTS, is_valid_help as k_valid,
                    FOURTH_SLOT_ITEM as K_FSI, loadout_conflict as k_conflict, get_help as k_get)
                from app.domains.wallet.loadout import set_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                for s in slots:
                    if s not in inv and s not in K_DEFAULTS:
                        await sio.emit('help_loadout_result', {'ok': False, 'msg': 'لا تملك إحدى المساعدات'}, to=sid); return
                # تعارض: تمرير × درع السترايك (حماية مزدوجة)
                conf = k_conflict(slots)
                if conf:
                    n1 = (k_get(conf[0]) or {}).get('name', conf[0])
                    n2 = (k_get(conf[1]) or {}).get('name', conf[1])
                    await sio.emit('help_loadout_result',
                        {'ok': False, 'msg': f'لا يمكن تجهيز "{n1}" مع "{n2}" معاً'}, to=sid)
                    return
                max_slots = k_slots(user.level or 0, owns_cosmetic(user.id, K_FSI))
                await sio.emit('help_loadout_result',
                    set_loadout_for_game(user.id, 'knowledge', slots, max_slots, k_valid), to=sid)
                return
            if game == 'whoami':
                from app.domains.games.whoami.helps import (get_slots_for_player as w_slots,
                    DEFAULT_LOADOUT as W_DEFAULTS, is_valid_help as w_valid,
                    FOURTH_SLOT_ITEM as W_FSI, loadout_conflict as w_conflict, get_help as w_get)
                from app.domains.wallet.loadout import set_loadout_for_game
                from app.domains.wallet.cosmetics import owns_cosmetic
                for s in slots:
                    if s not in inv and s not in W_DEFAULTS:
                        await sio.emit('help_loadout_result', {'ok': False, 'msg': 'لا تملك إحدى المساعدات'}, to=sid); return
                conf = w_conflict(slots)
                if conf:
                    n1 = (w_get(conf[0]) or {}).get('name', conf[0])
                    n2 = (w_get(conf[1]) or {}).get('name', conf[1])
                    await sio.emit('help_loadout_result',
                        {'ok': False, 'msg': f'لا يمكن تجهيز "{n1}" مع "{n2}" معاً'}, to=sid)
                    return
                max_slots = w_slots(user.level or 0, owns_cosmetic(user.id, W_FSI))
                await sio.emit('help_loadout_result',
                    set_loadout_for_game(user.id, 'whoami', slots, max_slots, w_valid), to=sid)
                return
            from app.domains.wallet.loadout import set_loadout
            from app.domains.games.huroof.helps import get_slots_for_player, DEFAULT_LOADOUT
            for s in slots:
                if s not in inv and s not in DEFAULT_LOADOUT:
                    await sio.emit('help_loadout_result', {'ok': False, 'msg': 'لا تملك إحدى المساعدات'}, to=sid); return
            max_slots = get_slots_for_player(user.level or 0, _owns_fourth_slot(user.id))
            await sio.emit('help_loadout_result', set_loadout(user.id, slots, max_slots), to=sid)
        finally:
            db.close()

    @sio.on('equip_cosmetic')
    async def equip_cosmetic(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            item = find_item((data or {}).get('itemId'))
            if not item or item['category'] not in ('avatar', 'theme'):
                await sio.emit('equip_result', {'ok': False, 'msg': 'عنصر غير قابل للتجهيز'}, to=sid); return
            from app.domains.wallet.cosmetics import owns_cosmetic
            if item['id'] not in get_base_owned_cosmetics() and not owns_cosmetic(user.id, item['id']):
                await sio.emit('equip_result', {'ok': False, 'msg': 'لا تملك هذا العنصر'}, to=sid); return
            from app.domains.wallet.equipped import set_equipped
            set_equipped(user.id, item['category'], item['id'])
            applied = None
            if item['category'] == 'avatar' and item.get('asset'):
                avatar_file = item['asset'].split('/')[-1]
                from sqlalchemy import text
                from app.infrastructure.database import engine
                with engine.connect() as conn:
                    conn.execute(text("UPDATE users SET avatar = :a WHERE id = :u"), {"a": avatar_file, "u": user.id})
                    conn.commit()
                applied = avatar_file
            await sio.emit('equip_result', {
                'ok': True, 'msg': f"تم تجهيز {item['name']} ✅", 'itemId': item['id'],
                'category': item['category'], 'applied': applied or item['id'], 'asset': item.get('asset'),
            }, to=sid)
        finally:
            db.close()

    @sio.on('get_equipped')
    async def get_equipped_handler(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user: return
        try:
            from app.domains.wallet.equipped import get_equipped
            await sio.emit('equipped_data', {'equipped': get_equipped(user.id)}, to=sid)
        finally:
            db.close()