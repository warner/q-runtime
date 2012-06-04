
import json
from twisted.trial import unittest
from .common import ServerBase
from ..memory import create_memory, Memory
from ..urbject import create_urbject, create_power_for_memid, \
     Urbject, Invocation, PackedPower

F1 = """
def call(args, power):
    debug('I have power!')
"""

F2 = """
def call(args, power):
    power['memory']['counter'] += args['delta']
"""

F3 = """
F3a = '''
def call(args, power):
    power['memory']['counter'] += 10
'''

def call(args, power):
    u2 = power['make_urbject'](F3a, power)
    power['memory']['u2'] = u2
"""

F4 = """
def call(args, power):
    debug('make_urbject' in power)
"""

F5 = """
def call(args, power):
    power['memory']['argfoo'] = args['foo']
"""

F6 = """
F6a = '''
def call(args, power):
    power['memory']['counter'] += 10
    power['memory']['counter'] += power['extra']
'''

def call(args, power):
    u2 = power['make_urbject'](F6a, add(power, {'extra': 5}))
    power['memory']['u2'] = u2
"""

F7 = """
F7a = '''
def call(args, power):
    mem, deltas = args
    assert isinstance(deltas, set) # ref.call() can take arbitrary local args
    # including references to Memory objects, or pieces of them, on which
    # changes will be visible to the parent as soon as we return
    mem['counter'] += 10
    # and our parent can add extra powers
    power['memory']['counter'] += power['extra']
    for delta in deltas:
        power['memory']['counter'] += delta
    return 20
'''

F7b = '''
def call(delta, power):
    # or objects can be given independent memory
    power['memory']['counter'] += delta
    return 30
'''

def call(args, power):
    u2 = power['make_urbject'](F7a, add(power, {'extra': 5}))
    power['memory']['counter'] = 0;
    args = (power['memory'], set([2,1]))
    rc = u2.call(args) # this is synchronous
    assert rc == 20, rc
    power['memory']['rc'] = rc
    u3_power = add(power, {'memory': {'counter': 0}}) # independent memory
    u3 = power['make_urbject'](F7b, u3_power)
    rc = u3.call(100)
    assert rc == 30
    assert power['memory']['counter'] == 18, power['memory']['counter']
"""

class Test(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)
        u = Urbject(self.server, self.db, urbjid)
        del u

    def test_execute(self):
        msgs = []
        powid = create_power_for_memid(self.db)
        i = Invocation(self.server, self.db, F1, powid)
        i.invoke("{}", "{}", "from_vatid", debug=msgs.append)
        self.failUnlessEqual(msgs, ["I have power!"])

    def test_memory(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        i = Invocation(self.server, self.db, F2, powid)
        i.invoke('{"delta": 1}', "{}", "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_static_data()["counter"], 1)

    def test_invoke(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F2)
        u = Urbject(self.server, self.db, urbjid)
        u.invoke('{"delta": 2}', "{}", "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_static_data()["counter"], 2)

    def test_deny_make_urbject(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=False)
        urbjid = create_urbject(self.db, powid, F4)
        msgs = []
        u = Urbject(self.server, self.db, urbjid)
        u.invoke("{}", "{}", "from_vatid", debug=msgs.append)
        self.failUnlessEqual(msgs, [False])

    def test_sub_urbject(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F3)
        Urbject(self.server, self.db, urbjid).invoke("{}", "{}", "from_vatid")
        m = Memory(self.db, memid)
        m_data, m_clist = m.get_data()
        u2id = m_clist[str(m_data["u2"]["clid"])][1]
        Urbject(self.server, self.db, u2id).invoke("{}", "{}", "from_vatid")
        self.failUnlessEqual(m.get_static_data()["counter"], 10)

    def pack_args(self, args, clist):
        return PackedPower(json.dumps(args), json.dumps(clist))

    def test_invoke_args(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F5)
        u = Urbject(self.server, self.db, urbjid)
        args = json.dumps({"foo": {"__power__": "reference", "clid": "1"}})
        args_clist = json.dumps({"1": "foo-urbjid"})
        # TODO: replace foo-urbjid with something real (local or remote)
        u.invoke(args, args_clist, "from_vatid")
        m = Memory(self.db, memid)
        m_data, m_clist = m.get_data()
        fooid = m_clist[str(m_data["argfoo"]["clid"])]
        self.failUnlessEqual(fooid, "foo-urbjid")

    def test_add(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F6)
        Urbject(self.server, self.db, urbjid).invoke("{}", "{}", "from_vatid")
        m = Memory(self.db, memid)
        m_data, m_clist = m.get_data()
        u2id = m_clist[str(m_data["u2"]["clid"])][1]
        Urbject(self.server, self.db, u2id).invoke("{}", "{}", "from_vatid")
        self.failUnlessEqual(m.get_static_data()["counter"], 15)

    def test_call_sync(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F7)
        Urbject(self.server, self.db, urbjid).invoke("{}", "{}", "from_vatid")
        # that will throw an exception unless it worked, but check anyways in
        # case the exception-handling code gets broken
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_static_data()["counter"], 18)
        self.failUnlessEqual(m.get_static_data()["rc"], 20)
