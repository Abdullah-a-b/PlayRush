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
