"""خصم المتجر ومنح المشتريات داخل معاملة واحدة."""
from sqlalchemy import text
from app.domains.users.models import User


def purchase(db, user_id, item):
    # تهيئة جداول الملكية تسبق معاملة الشراء، ولا يحدث خصم خارجها.
    from app.domains.wallet.help_inventory import _init as init_inventory
    from app.domains.wallet.cosmetics import _init as init_cosmetics
    init_inventory(); init_cosmetics()
    try:
        user = db.query(User).filter(User.id == user_id).populate_existing().with_for_update().first()
        if not user or user.is_banned:
            raise ValueError('الجلسة غير صالحة')
        if (user.level or 0) < item['unlock_level']:
            raise ValueError(f"يفتح في المستوى {item['unlock_level']}")
        currency, price = item['currency'], item['price']
        if currency not in {'coins','gems'} or price < 0:
            raise ValueError('سعر غير صالح')
        balance = getattr(user, currency) or 0
        if balance < price:
            raise ValueError('رصيد غير كافٍ')
        if item['category'] == 'help':
            db.execute(text('''INSERT INTO player_help_inventory (user_id, help_id, quantity)
                VALUES (:uid, :hid, 1) ON CONFLICT (user_id, help_id)
                DO UPDATE SET quantity=player_help_inventory.quantity+1'''),
                       {'uid':user_id,'hid':item['ref_id']})
        else:
            from app.domains.wallet.store_catalog import get_base_owned_cosmetics
            if item['id'] in get_base_owned_cosmetics():
                raise ValueError('تملك هذا العنصر مسبقًا')
            result = db.execute(text('''INSERT INTO player_cosmetics (user_id,item_id,category)
                VALUES (:uid,:iid,:cat) ON CONFLICT (user_id,item_id) DO NOTHING RETURNING item_id'''),
                               {'uid':user_id,'iid':item['id'],'cat':item['category']})
            if result.first() is None:
                raise ValueError('تملك هذا العنصر مسبقًا')
        setattr(user, currency, balance-price)
        wallet = {'coins':user.coins or 0,'gems':user.gems or 0}
        db.commit()
        return {'ok':True,'wallet':wallet}
    except ValueError as exc:
        db.rollback()
        return {'ok':False,'msg':str(exc)}
    except Exception:
        db.rollback()
        return {'ok':False,'msg':'لم تكتمل عملية الشراء؛ لم يُخصم شيء'}
