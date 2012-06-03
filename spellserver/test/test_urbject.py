
from twisted.trial import unittest
from .common import ServerBase
from ..memory import create_memory, Memory
from ..urbject import create_urbject, create_power_for_memid, get_power, \
     execute, Urbject

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
    u2id = power['make_urbject'](F3a, power)
    power['memory']['u2id'] = u2id
"""

F4 = """
def call(args, power):
    debug('make_urbject' in power)
"""

class Test(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F1)
        u = Urbject(self.db, urbjid)

    def test_execute(self):
        powid = create_power_for_memid(self.db)
        outer_power = get_power(self.db, powid)
        msgs = []
        execute(self.db, F1, {}, outer_power, "from_vatid", debug=msgs.append)
        self.failUnlessEqual(msgs, ["I have power!"])

    def test_memory(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        outer_power = get_power(self.db, powid)
        msgs = []
        execute(self.db, F2, {"delta": 1}, outer_power, "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 1)

    def test_invoke(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, F2)
        u = Urbject(self.db, urbjid)
        u.invoke({"delta": 2}, "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 2)

    def test_deny_make_urbject(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=False)
        urbjid = create_urbject(self.db, powid, F4)
        msgs = []
        Urbject(self.db, urbjid).invoke({}, "from_vatid", debug=msgs.append)
        self.failUnlessEqual(msgs, [False])

    def test_sub_urbject(self):
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid, grant_make_urbject=True)
        urbjid = create_urbject(self.db, powid, F3)
        Urbject(self.db, urbjid).invoke({}, "from_vatid")
        m = Memory(self.db, memid)
        u2id = m.get_data()["u2id"]
        Urbject(self.db, u2id).invoke({}, "from_vatid")
        self.failUnlessEqual(m.get_data()["counter"], 10)
