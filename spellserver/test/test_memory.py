
import os
from StringIO import StringIO
from twisted.trial import unittest
from ..node import Node
from ..scripts.create_node import create_node
from .. import memory, urbject

class Memory(unittest.TestCase):
    def setUp(self):
        self.basedir = self.mktemp()
        create_node({"basedir": self.basedir, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile = os.path.join(self.basedir, "control.db")
        self.node = Node(self.basedir, dbfile)
        self.server = self.node.server
        self.db = self.server.db

    def test_create(self):
        memid = memory.create_memory(self.db)
        self.failUnless(memid.startswith("mem0-"), memid)
