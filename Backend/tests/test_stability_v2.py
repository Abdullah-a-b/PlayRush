import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.domains.games.core_manager import candidate_pairs


class QueueBoundaries(unittest.TestCase):
    def test_older_wait_opens_class_but_never_bypasses_blocks(self):
        for threshold, shared_ip, previous, friends in [(0,False,False,False),(5,False,True,False),
                (10,True,False,False),(15,True,True,False),(20,False,False,True)]:
            a = dict(user_id=1,time=100,ip='x')
            b = dict(user_id=2,time=100+threshold,ip='x' if shared_ip else 'y')
            args = ({(1,2)} if friends else set(), {(1,2)} if previous else set())
            self.assertEqual(candidate_pairs([a,b],set(),*args,b['time']),[(0,1)])
            if threshold:
                self.assertEqual(candidate_pairs([a,b],set(),*args,b['time']-.01),[])
            self.assertEqual(candidate_pairs([a,b],{(1,2)},*args,b['time']),[])
            self.assertEqual(candidate_pairs([a,b],set(),*args,130),[])

    def test_first_entry_does_not_hold_others(self):
        entries=[dict(time=0,user_id=i,ip=str(i)) for i in (1,2,3)]
        self.assertEqual(candidate_pairs(entries,{(1,2),(1,3)},set(),set(),1),[(1,2)])


