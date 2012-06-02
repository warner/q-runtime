
import os
from StringIO import StringIO
from twisted.trial import unittest
from ..node import Node
from ..scripts.create_node import create_node
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

class Test(unittest.TestCase):
    def setUp(self):
        self.basedir = self.mktemp()
        create_node({"basedir": self.basedir, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile = os.path.join(self.basedir, "control.db")
        self.node = Node(self.basedir, dbfile)
        self.server = self.node.server
        self.db = self.server.db

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
