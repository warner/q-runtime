
import os
from StringIO import StringIO
from ..scripts.create_node import create_node
from ..node import Node

class ServerBase:
    def setUp(self):
        self.basedir = self.mktemp()
        create_node({"basedir": self.basedir, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile = os.path.join(self.basedir, "control.db")
        self.node = Node(self.basedir, dbfile)
        self.server = self.node.server
        self.db = self.server.db
