
import json
from twisted.trial import unittest
from .common import ServerBase, TwoServerBase
from .pollmixin import PollMixin
from ..memory import create_memory, Memory
from ..urbject import create_urbject, create_power_for_memid


F1 = """
def call(args, power):
    power['memory']['argfoo'] = args['foo']
"""

class Local(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)

        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps({"foo": 123}),
               "args_clist_json": json.dumps({}),
               }

        self.server.process_request(msg, "from-vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_static_data()["argfoo"], 123)

    def test_reference(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)

        args = {"foo": {"__power__": "reference", "clid": "1"}}
        args_clist = {"1": "foo-urbjid"}
        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps(args_clist),
               }

        self.server.process_request(msg, "from-vatid")
        m = Memory(self.db, memid)
        m_data, m_clist = m.get_data()
        fooid = m_clist[str(m_data["argfoo"]["clid"])]
        self.failUnlessEqual(fooid, "foo-urbjid")

class Remote(TwoServerBase, PollMixin, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)

        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps({"foo": 123}),
               "args_clist_json": json.dumps({}),
               }
        msg_json = json.dumps(msg)
        self.server2.send_message(self.server.vatid, msg_json)
        # now wait for the first node to process it
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            m = Memory(self.db, memid)
            self.failUnlessEqual(m.get_static_data()["argfoo"], 123)
        d.addCallback(_then)
        return d

    def OFF_test_reference(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)

        args = {"foo": {"__power__": "reference", "clid": "1"}}
        args_clist = {"1": "foo-urbjid"}
        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps(args_clist),
               }

        self.server.process_request(msg, "from-vatid")
        m = Memory(self.db, memid)
        m_data, m_clist = m.get_data()
        fooid = m_clist[str(m_data["argfoo"]["clid"])]
        self.failUnlessEqual(fooid, "foo-urbjid")
