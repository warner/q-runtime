
import os
from StringIO import StringIO
from twisted.trial import unittest
from ..node import Node
from ..scripts.create_node import create_node

class State(unittest.TestCase):
    def setUp(self):
        self.basedir = self.mktemp()
        create_node({"basedir": self.basedir, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile = os.path.join(self.basedir, "control.db")
        self.node = Node(self.basedir, dbfile)
        self.server = self.node.server

    def test_create(self):
        objid = self.server.create_object()

