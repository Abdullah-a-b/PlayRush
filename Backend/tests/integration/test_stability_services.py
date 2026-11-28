import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.domains.games.core_manager import candidate_pairs


@unittest.skipUnless(os.environ.get("PLAYRUSH_TEST_POSTGRES")=="1","dedicated test PostgreSQL required")
class WalletIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.infrastructure.database import register_models, Base, engine
        register_models()
        Base.metadata.create_all(engine)

    def setUp(self):
        from app.infrastructure.database import SessionLocal
        from app.domains.users.models import User
        self.db=SessionLocal
        with SessionLocal.begin() as db:
            users=[User(email=uuid.uuid4().hex+"@test.invalid",is_verified=True) for _ in range(2)]
            db.add_all(users);db.flush()
            self.ids=[u.id for u in users]

    def test_hybrid_matchmaking_and_background_review_all_modes(self):
        from app.core import match_review
        from app.domains.games.core_manager import ranked_pairs
        from app.domains.games.models import MatchReview
        from app.domains.users.models import GameStat, User
        from app.domains.wallet.reward_service import save_match_sync
        modes = ["bank", "knowledge", "career", "whoami", "huroof"]
        with self.db.begin() as db:
            third = User(email=uuid.uuid4().hex+"@test.invalid", is_verified=True)
            db.add(third)
            db.flush()
            ids = [*self.ids, third.id]
            for i, mode in enumerate(modes):
                close = 1 + i % 2
                for j, uid in enumerate(ids):
                    db.add(GameStat(user_id=uid, game_mode=mode, wins=10 if j in (0, close) else 0,
                                    losses=0 if j in (0, close) else 10))
        mids = []
        for i, mode in enumerate(modes):
            now = time.time()
            entries = [dict(user_id=uid, time=now - (2 if j==0 else 1), ip=str(uid)) for j, uid in enumerate(ids)]
            self.assertEqual(ranked_pairs(entries, mode)[0], (0, 1+i%2))
        for mode in modes:
            mid = uuid.uuid4().hex
            mids.append(mid)
            save_match_sync(dict(user_id=ids[0], alternatives=1), dict(user_id=ids[1], alternatives=2),
                            mode, dict(match_id=mid))
        with patch.object(match_review, "classify_batch", side_effect=TimeoutError):
            match_review.run_batch()
        with self.db() as db:
            for mid in mids:
                review = db.get(MatchReview, mid)
                self.assertEqual((review.local_label, review.status, review.alternatives), ("ordinary","local",1))
        mid = uuid.uuid4().hex
        save_match_sync(dict(user_id=ids[0]), dict(user_id=ids[1]), "bank", dict(match_id=mid))
        with patch.object(match_review, "classify_batch", side_effect=lambda features: ["insufficient"]*len(features)):
            match_review.run_batch()
        with self.db() as db:
            self.assertEqual(db.get(MatchReview, mid).ai_label, "insufficient")

    @unittest.skipUnless(os.environ.get("PLAYRUSH_TEST_REDIS"), "dedicated Redis required")
    def test_rate_survives_new_session_and_db_suspension(self):
        import asyncio
        import redis.asyncio as redis
        from datetime import datetime, timedelta
        from app.core.anticheat import check_account_rate
        from app.core.cluster import _admit_game_action
        from app.domains.games.models import FairPlayAccount
        uid = self.ids[0]
        room = {"type":"public", "players":[{"sid":"second", "user_id":uid}],
                "user_ids":{"first":uid, "second":uid}}
        with self.db.begin() as db:
            db.add(FairPlayAccount(user_id=uid, updated=datetime.utcnow(),
                                   suspended_until=datetime.utcnow()+timedelta(minutes=5)))
        async def exercise():
            client = redis.Redis.from_url(os.environ["PLAYRUSH_TEST_REDIS"], decode_responses=True)
            with patch("app.infrastructure.redis_client.get_redis", return_value=client):
                self.assertIsNone(await check_account_rate("first", "test", 1, room))
                self.assertIsNotNone(await check_account_rate("second", "test", 1, room))
                self.assertFalse(await _admit_game_action("bank_buzz", room, "second"))
            await client.aclose()
        asyncio.run(exercise())

    def test_premium_retry_after_season_rollover(self):
        from app.domains.wallet import pass_service as ps
        from app.domains.users.models import User
        uid = self.ids[0]
        key = str(uuid.uuid4())
        with self.db.begin() as db:
            db.get(User,uid).gems = 3*ps.EC.PREMIUM_PASS_PRICE_GEMS
        with self.db() as db, patch.object(ps, "season_key", return_value="2026-S11"):
            original = ps.buy_premium(db, uid, key, "2026-S11")
            self.assertTrue(original["ok"])
        with self.db() as db, patch.object(ps, "season_key", return_value="2026-S12"):
            self.assertEqual(ps.buy_premium(db,uid,key,"2026-S11"), original)
            self.assertFalse(ps.buy_premium(db,uid,key,"2026-S12")["ok"])
            self.assertFalse(ps.get_or_create_pass(db,uid).is_premium)
            self.assertEqual(db.get(User,uid).gems,original["gems_left"])

    def test_process_death_during_and_after_financial_commit(self):
        import subprocess, sys
        from datetime import datetime, timedelta
        from app.domains.games.match_recovery import register, maintain, last_result
        from app.domains.games.models import PublicMatchLease, PairSettlement
        worker = """
import os,sys
from unittest.mock import patch
from app.domains.wallet import reward_service as service
a,b,mid,point = sys.argv[1:]
players = [dict(user_id=int(uid)) for uid in (a,b)]
if point == "before":
    with patch.object(service, "_apply_progression", side_effect=lambda *a,**k:os._exit(45)):
        service.save_match_sync(*players,"bank",dict(match_id=mid))
else:
    service.save_match_sync(*players,"bank",dict(match_id=mid))
    os._exit(46)
"""
        players = [dict(user_id=uid) for uid in self.ids]
        for point, expected_exit in (("before",45),("after",46)):
            mid = uuid.uuid4().hex
            room = dict(code=mid[:10], players=players)
            register(room,mid)
            from app.core.cluster import WORKER_ID
            result = subprocess.run([sys.executable,"-c",worker,*map(str,self.ids),mid,point],
                env={**os.environ, "WORKER_ID":WORKER_ID}, timeout=20)
            self.assertEqual(result.returncode, expected_exit)
            with self.db.begin() as db:
                db.get(PublicMatchLease,mid).heartbeat = datetime.utcnow()-timedelta(days=1)
            maintain([])
            with self.db() as db:
                self.assertEqual(db.get(PairSettlement,mid) is not None, point=="after")
            self.assertEqual(last_result(room["code"],self.ids[0]),
                             {"status":"settled","result":"win"} if point=="after" else {"status":"cancelled"})

    def test_reservation_expires_before_either_player_joins(self):
        from datetime import datetime, timedelta
        from app.domains.games.match_recovery import register, maintain, last_result
        from app.domains.games.models import PublicMatchLease
        mid = uuid.uuid4().hex
        room = dict(code=mid[:10], players=[dict(user_id=uid) for uid in self.ids])
        register(room, mid, reserved=True)
        with self.db.begin() as db:
            row = db.get(PublicMatchLease, mid)
            self.assertEqual(row.status, "reserved")
            row.heartbeat = datetime.utcnow()-timedelta(days=1)
        maintain([])
        self.assertEqual(last_result(room["code"], self.ids[0]), {"status":"cancelled"})
        with self.assertRaises(RuntimeError):
            register(room, mid)

    def test_independent_purchases_cannot_overdraw(self):
        from app.domains.wallet.purchase_service import purchase
        from app.domains.users.models import User
        uid = self.ids[0]
        with self.db.begin() as db:
            db.get(User, uid).coins = 10
        item = dict(id="budget_test", ref_id="budget_test", price=3, currency="coins",
                    unlock_level=0, category="help")
        def buy(_):
            with self.db() as db:
                return purchase(db, uid, item, str(uuid.uuid4()))["ok"]
        with ThreadPoolExecutor(8) as pool:
            self.assertEqual(sum(pool.map(buy, range(20))),3)
        with self.db() as db:
            self.assertEqual(db.get(User, uid).coins,1)

    def test_expired_owner_refund_and_settlement_are_exclusive(self):
        from datetime import datetime, timedelta
        from app.domains.games.match_recovery import register, maintain, last_result
        from app.domains.games.models import PublicMatchLease
        from app.domains.wallet.help_inventory import add_help, consume_help, get_quantity
        from app.domains.wallet.reward_service import save_match_sync
        players = [dict(user_id=uid) for uid in self.ids]
        for settled in (False, True):
            mid = uuid.uuid4().hex
            room = dict(code=mid[:10], players=players)
            register(room, mid)
            add_help(self.ids[0], "test_recovery", 1)
            before = get_quantity(self.ids[0], "test_recovery")
            self.assertTrue(consume_help(self.ids[0], "test_recovery", mid))
            if settled:
                save_match_sync(*players, "bank", dict(match_id=mid))
            with self.db.begin() as db:
                db.get(PublicMatchLease, mid).heartbeat = datetime.utcnow()-timedelta(days=1)
            with ThreadPoolExecutor(2) as pool:
                list(pool.map(maintain, [[], []]))
            save_match_sync(*players, "bank", dict(match_id=mid))
            self.assertEqual(last_result(room["code"], self.ids[0])["status"], "settled" if settled else "cancelled")
            self.assertEqual(get_quantity(self.ids[0], "test_recovery"), before-int(settled))

    def test_fifty_purchase_retries(self):
        from app.domains.wallet.purchase_service import purchase
        from app.domains.users.models import User
        from sqlalchemy import text
        uid = self.ids[0]
        item = dict(id="test_help", ref_id="test_help", price=3, currency="coins",
                    unlock_level=0, category="help")
        with self.db.begin() as db:
            db.get(User, uid).coins = 10
        key = str(uuid.uuid4())
        def buy(_):
            with self.db() as db:
                return purchase(db, uid, item, key)
        with ThreadPoolExecutor(10) as pool:
            results = list(pool.map(buy, range(50)))
        self.assertTrue(all(r["ok"] and r["wallet"]["coins"] == 7 for r in results))
        with self.db() as db:
            self.assertEqual(db.get(User, uid).coins, 7)
            self.assertFalse(purchase(db, uid, dict(item, id="another_item"), key)["ok"])
            self.assertEqual(db.execute(text("select quantity from player_help_inventory where user_id=:u and help_id='test_help'"), {"u":uid}).scalar(), 1)

    def test_entire_pass_and_cosmetic_ownership(self):
        from app.domains.wallet import pass_service as service
        from app.domains.wallet import economy_config as ec
        from sqlalchemy import text
        uid=self.ids[0]
        with patch.object(service,"season_key",return_value="2026-S12"),self.db() as db:
            record=service.get_or_create_pass(db,uid)
            record.pass_xp=ec.PASS_XP_PER_TIER*30
            record.is_premium=True
            db.commit()
            gems={}
            for track in ("free","premium"):
                gems[track]=0
                for tier in range(1,31):
                    result=service.claim_tier(db,uid,tier,track)
                    self.assertTrue(result["ok"])
                    gems[track]+=result["reward"].get("gems",0)
                    self.assertFalse(service.claim_tier(db,uid,tier,track)["ok"])
            self.assertEqual(gems,{"free":30,"premium":ec.PREMIUM_PASS_GEM_PAYBACK})
            owned=db.execute(text("select count(*) from player_cosmetics where user_id=:u"),{"u":uid}).scalar()
            self.assertEqual(owned,3)

    @unittest.skipUnless(os.environ.get("PLAYRUSH_TEST_REDIS"),"dedicated Redis required")
    def test_atomic_queue_reservation(self):
        import asyncio
        import json
        import redis.asyncio as redis
        from unittest.mock import AsyncMock
        from app.domains.games.sockets import matchmaking as mm
        case=uuid.uuid4().hex
        async def exercise():
            client=redis.Redis.from_url(os.environ["PLAYRUSH_TEST_REDIS"],decode_responses=True)
            entries=[dict(user_id=u,sid=case+str(u),name=str(u),avatar="",ip=str(u),time=time.time()) for u in self.ids]
            prefix=mm._MMQ+case
            for e in entries:
                await client.set("pr:conn:"+e["sid"],"sender",ex=20)
                await client.set(mm._MMQ_UID+str(e["user_id"]),e["sid"],ex=20)
                await client.rpush(prefix,json.dumps(e))
            socket=AsyncMock()
            def make_room(a,b,mode,code):
                return code,[a,b],{}
            with patch.object(mm,"create_match_room",side_effect=make_room) as create:
                await asyncio.gather(*(mm._cluster_try_match(socket,client,case) for _ in range(3)))
                self.assertEqual(create.call_count,1)
            self.assertEqual(socket.emit.await_count,2)
            self.assertEqual(await client.llen(prefix),0)
            self.assertEqual(await client.get("pr:mm_active:"+str(self.ids[0])),await client.get("pr:mm_active:"+str(self.ids[1])))
            await client.aclose()
        asyncio.run(exercise())

    def test_concurrent_xp_and_rollback(self):
        from app.domains.wallet.pass_service import add_pass_xp, get_or_create_pass, claim_tier
        uid=self.ids[0]
        def add(_):
            with self.db.begin() as db:
                add_pass_xp(db,uid,3)
        with ThreadPoolExecutor(10) as pool:
            list(pool.map(add,range(100)))
        with self.db() as db:
            add_pass_xp(db,uid,50)
            db.rollback()
            self.assertEqual(get_or_create_pass(db,uid).pass_xp,300)
            self.assertFalse(claim_tier(db,uid,1,"other")["ok"])

    def test_shadow_case_survives_unrewarded_fifth_match_and_retry(self):
        from app.domains.wallet.reward_service import save_match_sync
        from app.domains.games.models import ShadowOutcome, FairPlayAccount
        a, b = [dict(user_id=i) for i in self.ids]
        for _ in range(5):
            result = dict(match_id=uuid.uuid4().hex, reason="surrender")
            save_match_sync(a, b, "bank", result)
            save_match_sync(a, b, "bank", result)
        with self.db() as db:
            rows = db.query(ShadowOutcome).filter_by(low_id=min(self.ids)).all()
            self.assertEqual(len(rows), 5)
            self.assertEqual([r.review_reason for r in rows if r.review_reason],
                             ["five_same_winner_with_repeated_surrenders"])
            self.assertIsNone(db.get(FairPlayAccount, self.ids[0]))
            self.assertIsNone(db.get(FairPlayAccount, self.ids[1]))

    def test_five_matches_duplicate_and_partial_failure(self):
        from app.domains.wallet.reward_service import save_match_sync
        from app.domains.games.models import PairSettlement
        from app.domains.users.models import User
        a,b=[dict(user_id=i) for i in self.ids]
        mid=uuid.uuid4().hex
        with patch("app.domains.wallet.reward_service._apply_progression",side_effect=ValueError("injected")):
            save_match_sync(a,b,"bank",dict(match_id=mid))
        with self.db() as db:
            self.assertIsNone(db.get(PairSettlement,mid))
        for mode in ["bank","career","whoami","knowledge","huroof"]:
            mid=uuid.uuid4().hex
            for _ in range(2):
                save_match_sync(a,b,mode,dict(match_id=mid))
        with self.db() as db:
            self.assertEqual(db.get(User,self.ids[0]).wins,4)
            self.assertEqual(db.query(PairSettlement).filter_by(low_id=self.ids[0]).count(),5)

@unittest.skipUnless(os.environ.get("PLAYRUSH_TEST_REDIS"),"dedicated Redis required")
class OwnerRouting(unittest.TestCase):
    def test_events_are_handled_only_by_live_owner(self):
        import subprocess, sys
        url=os.environ["PLAYRUSH_TEST_REDIS"]
        prefix="test-"+uuid.uuid4().hex
        env={**os.environ,"REDIS_URL":url,"CASE_ID":prefix}
        worker="""
import asyncio,os
from app.core import cluster as c
from app.domains.games.core_manager import rooms
from app.infrastructure.redis_client import get_redis
async def main():
    prefix=os.environ['CASE_ID']
    modes=('huroof','bank','career','whoami','knowledge')
    class Socket:
        handlers={'/':{m+'_buzz':True for m in modes}}
        async def _trigger_event(self,event,ns,sid,data):
            await get_redis().rpush(prefix+':events',event)
        async def enter_room(self,*args): pass
        async def leave_room(self,*args): pass
        async def emit(self,event,*args,**kwargs):
            await get_redis().rpush(prefix+':feedback',event)
    sock=Socket()
    c.patch(sock)
    if os.environ['ROLE']=='owner':
        rooms[prefix]={'players':[{'sid':'A'}]}
        await c.claim_room(prefix)
        await c.cluster_subscriber_loop(sock)
    else:
        for mode in modes:
            await sock._trigger_event(mode+'_buzz','/','A',{'roomCode':prefix})
asyncio.run(main())
"""
        import redis
        r=redis.Redis.from_url(url,decode_responses=True)
        def proc(role):
            return subprocess.Popen([sys.executable,'-c',worker],env={**env,'ROLE':role,'WORKER_ID':prefix+role},
                                    stdout=subprocess.DEVNULL)
        owner=proc('owner')
        try:
            for _ in range(100):
                if r.pubsub_numsub('pr:cluster:'+prefix+'owner')[0][1]:break
                time.sleep(.05)
            self.assertEqual(proc('sender').wait(15),0)
            for _ in range(100):
                if r.llen(prefix+':events')==5:break
                time.sleep(.05)
            self.assertEqual(r.lrange(prefix+':events',0,-1),[m+'_buzz' for m in ('huroof','bank','career','whoami','knowledge')])
            owner.kill();owner.wait(5)
            self.assertEqual(proc('sender').wait(15),0)
            self.assertEqual(r.llen(prefix+':events'),5)
            self.assertEqual(r.llen(prefix+':feedback'),5)
        finally:
            if owner.poll() is None:owner.kill();owner.wait(5)
            r.delete(prefix+':events',prefix+':feedback','pr:room_owner:'+prefix)
            r.close()
