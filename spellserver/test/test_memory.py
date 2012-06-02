
import os
from StringIO import StringIO
from twisted.trial import unittest
from ..node import Node
from ..scripts.create_node import create_node
from ..memory import create_memory, Memory

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
        self.failUnless(memid.startswith("mem0-"), memid)
        m = Memory(self.db, memid)
        data = m.get_data()
        self.failUnlessEqual(data, {})
        data["hello"] = "world"
        data["subdir"] = {"key": 123}
        m.save()
        m2 = Memory(self.db, memid)
        self.failUnlessEqual(m2.get_data(), {"hello": "world",
                                             "subdir": {"key": 123}})
