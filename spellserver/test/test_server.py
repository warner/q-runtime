
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

F2 = """
def call(args, power):
    args['ref'].send({'foo': 34})
"""

F3 = """
F3a = '''
def call(args, power):
    power['memory']['argfoo'] = args['foo']
'''

def call(args, power):
    u2 = power['make_urbject'](F3a, power)
    u2.send({'foo': 56})
"""

class Local(ServerBase, PollMixin, unittest.TestCase):

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

    def test_loopback(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)

        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps({"foo": 123}),
               "args_clist_json": json.dumps({}),
               }
        msg_json = json.dumps(msg)
        self.server.send_message(self.server.vatid, msg_json) # to yourself
        # now wait for the first node to process it
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            m = Memory(self.db, memid)
            self.failUnlessEqual(m.get_static_data()["argfoo"], 123)
        d.addCallback(_then)
        return d

    def test_send_from_sandbox(self):
        memid_1 = create_memory(self.db)
        powid_1 = create_power_for_memid(self.db, memid_1)
        urbjid_1 = create_urbject(self.db, powid_1, F1)

        memid_2 = create_memory(self.db)
        powid_2 = create_power_for_memid(self.db, memid_2)
        urbjid_2 = create_urbject(self.db, powid_2, F2)

        #urb_2.add_reference_to_power("ref", urbjid_1)

        # trigger F2({ref:F1})
        args = {"ref": {"__power__": "reference", "clid": "1"}}
        args_clist = {"1": urbjid_1}
        msg = {"command": "invoke",
               "urbjid": urbjid_2,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps(args_clist),
               }

        self.server.process_request(msg, "from-vatid")
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            m = Memory(self.db, memid_1)
            m_data, m_clist = m.get_data()
            self.failUnlessEqual(m_data["argfoo"], 34)
        d.addCallback(_then)
        return d

    def test_make_and_send(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F3)

        # trigger F3()
        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps({}),
               "args_clist_json": json.dumps({}),
               }

        self.server.process_request(msg, "from-vatid")
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            m = Memory(self.db, memid)
            m_data, m_clist = m.get_data()
            self.failUnlessEqual(m_data["argfoo"], 56)
        d.addCallback(_then)
        return d

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

            # send a second one, make sure the DB msgnum updater works
            msg = {"command": "invoke",
                   "urbjid": urbjid,
                   "args_json": json.dumps({"foo": 456}),
                   "args_clist_json": json.dumps({}),
                   }
            msg_json = json.dumps(msg)
            self.server2.send_message(self.server.vatid, msg_json)
            return self.poll(lambda: self.server._debug_processed_counter >= 2)
        d.addCallback(_then)
        def _then2(ign):
            m = Memory(self.db, memid)
            self.failUnlessEqual(m.get_static_data()["argfoo"], 456)
        d.addCallback(_then2)
        return d

class Poke(TwoServerBase, PollMixin, unittest.TestCase):
    def test_poke(self):
        self.server.poke("poke")
        # that doesn't actually do anything

    def test_create_memory(self):
        msg = self.server.poke("create-memory")
        self.failUnless(msg.startswith("created memory "), msg)
        memid = msg.split()[2]
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_static_data(), {})

    def test_send(self):
        self.server2.poke("send %s" % self.server.vatid)
        # now wait for the first node to process it
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            # the message sent by 'poke send' is ignored
            return
        d.addCallback(_then)
        return d

    def test_execute(self):
        memid = create_memory(self.db)

        self.server2.poke("execute %s %s" % (self.server.vatid, memid))
        # now wait for the first node to process it
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            # the dummy code run by 'poke execute' doesn't do anything
            return
        d.addCallback(_then)
        return d

    def test_invoke(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)

        self.server2.poke("invoke %s %s" % (self.server.vatid, urbjid))
        # now wait for the first node to process it
        d = self.poll(lambda: self.server._debug_processed_counter >= 1)
        def _then(ign):
            m = Memory(self.db, memid)
            self.failUnlessEqual(m.get_static_data()["argfoo"], 12)
        d.addCallback(_then)
        return d
