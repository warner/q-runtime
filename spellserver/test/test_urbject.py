
import json
from twisted.trial import unittest
from .common import ServerBase
from ..memory import create_memory, Memory
from ..urbject import create_urbject, create_power_for_memid, Urbject
from ..turn import Turn

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

F8b = """
def call(args, power):
    power['memory']['counter'] = 222
"""

F8a = """
F8b = %r
def call(args, power):
    args['mem']['counter'] += 10
    power['memory']['counter'] += 5
    # F8b should be created with a memory object that is a copy of this one,
    # not a persistent reference. Only stack frames (Invocations) which were
    # born with this memory object are allowed to grant persistent access to
    # it.
    child_power = add(power, {'memory': args['mem']})
    return power['make_urbject'](F8b, child_power)
""" % F8b

F8 = """
F8a = %r

def call(args, power):
    power['memory']['counter'] = 0;
    f8a = power['make_urbject'](F8a, add(power, {'memory': {'counter': 0}}))
    power['memory']['f8a'] = f8a
    # hey f8a: you can change the memory I give you
    f8b = f8a.call({'mem': power['memory']}) # this is synchronous
    # but you can't put it in the power you grant to f8b
    f8b.call({})
    power['memory']['f8b'] = f8b
    assert power['memory']['counter'] == 10, power['memory']['counter']
""" % F8a

class Test(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)
        u = Urbject(self.server, self.db, urbjid)
        del u

    def invoke_urbjid(self, urbjid, args_json, debug=None):
        assert debug is None or callable(debug)
        t = self._make_turn()
        u = Urbject(self.server, self.db, urbjid)
        code, powid = u.get_code_and_powid()
        t.start_turn(code, powid, args_json, "from_vatid", debug)
        return t

    def _make_turn(self):
        return Turn(self.server, self.db)

    def test_execute(self):
        msgs = []
        powid = create_power_for_memid(self.db)
        t = self._make_turn()
        t.start_turn(F1, powid, "{}", "from_vatid", debug=msgs.append)
        self.failUnlessEqual(msgs, ["I have power!"])

    def test_memory(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        t = self._make_turn()
        t.start_turn(F2, powid, '{"delta": 1}', "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 1)

    def test_invoke(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F2)
        self.invoke_urbjid(urbjid, '{"delta": 2}')
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 2)

    def test_deny_make_urbject(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=False)
        urbjid = create_urbject(self.db, powid, F4)
        msgs = []
        self.invoke_urbjid(urbjid, "{}", debug=msgs.append)
        self.failUnlessEqual(msgs, [False])

    def test_sub_urbject(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F3)
        self.invoke_urbjid(urbjid, "{}")
        m = Memory(self.db, memid)
        u2id = m.get_data()["u2"]["swissnum"][1]
        self.invoke_urbjid(u2id, "{}")
        self.failUnlessEqual(m.get_data()["counter"], 10)

    def test_invoke_args(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F5)
        args = json.dumps({"foo": {"__power__": "reference",
                                   "swissnum": ("vatid","foo-urbjid")}})
        # TODO: replace foo-urbjid with something real (local or remote)
        self.invoke_urbjid(urbjid, args)
        m = Memory(self.db, memid)
        fooid = m.get_data()["argfoo"]["swissnum"]
        self.failUnlessEqual(fooid, [u"vatid",u"foo-urbjid"])

    def test_add(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F6)
        self.invoke_urbjid(urbjid, "{}")
        m = Memory(self.db, memid)
        u2id = m.get_data()["u2"]["swissnum"][1]
        self.invoke_urbjid(u2id, "{}")
        self.failUnlessEqual(m.get_data()["counter"], 15)

    def test_call_sync(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F7)
        self.invoke_urbjid(urbjid, "{}")
        # that will throw an exception unless it worked, but check anyways in
        # case the exception-handling code gets broken
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 18)
        self.failUnlessEqual(m.get_data()["rc"], 20)

    def test_call_no_shared_memory(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F8)
        t = self.invoke_urbjid(urbjid, "{}")
        mem = Memory(self.db, memid).get_data()
        self.failUnlessEqual(mem["counter"], 10)
        f8a_u = Urbject(self.server, self.db, mem["f8a"]["swissnum"][1])
        f8a_power = t.get_power(f8a_u.get_code_and_powid()[1])
        self.failUnlessEqual(f8a_power["memory"]["counter"], 5)
        f8b_u = Urbject(self.server, self.db, mem["f8b"]["swissnum"][1])
        f8b_power = t.get_power(f8b_u.get_code_and_powid()[1])
        self.failUnlessEqual(f8b_power["memory"]["counter"], 222)
