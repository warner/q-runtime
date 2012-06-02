
from twisted.trial import unittest
from .common import ServerBase
from ..memory import create_memory, Memory
from ..urbject import create_urbject, execute, Urbject, Power

F1 = """
def call(args, power):
    debug('I have power!')
"""

F2 = """
def call(args, power):
    power.memory['counter'] += args['delta']
"""

class Test(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        urbjid = create_urbject(self.db, memid, F1)
        u = Urbject(self.db, urbjid)

    def test_execute(self):
        memid = create_memory(self.db)
        msgs = []
        execute(self.db, F1, {}, memid, "from_vatid", debug=msgs.append)
        self.failUnlessEqual(msgs, ["I have power!"])

    def test_memory(self):
        memid = create_memory(self.db, {"counter": 0})
        execute(self.db, F2, {"delta": 1}, memid, "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 1)

    def test_invoke(self):
        memid = create_memory(self.db, {"counter": 0})
        urbjid = create_urbject(self.db, memid, F2)
        u = Urbject(self.db, urbjid)
        u.invoke({"delta": 2}, "from_vatid")
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_data()["counter"], 2)
