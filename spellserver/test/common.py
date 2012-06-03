
import os
from StringIO import StringIO
from twisted.application import service
from ..scripts.create_node import create_node
from ..node import Node

class ServerBase:
    def setUp(self):
        self.s = service.MultiService()
        self.basedir = self.mktemp()
        create_node({"basedir": self.basedir, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile = os.path.join(self.basedir, "control.db")
        self.node = Node(self.basedir, dbfile)
        self.server = self.node.server
        self.db = self.server.db
        self.node.setServiceParent(self.s)
        self.s.startService()

    def tearDown(self):
        return self.s.stopService()

class TwoServerBase:
    def setUp(self):
        self.s = service.MultiService()
        self.basedir = self.mktemp()
        create_node({"basedir": self.basedir, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile = os.path.join(self.basedir, "control.db")
        self.node = Node(self.basedir, dbfile)
        self.server = self.node.server
        self.db = self.server.db
        self.node.setServiceParent(self.s)

        self.basedir2 = self.mktemp()
        create_node({"basedir": self.basedir2, "webport": "tcp:0"},
                    stdout=StringIO(), stderr=StringIO())
        dbfile2 = os.path.join(self.basedir2, "control.db")
        self.node2 = Node(self.basedir2, dbfile2)
        self.server2 = self.node2.server
        self.db2 = self.server2.db
        self.node2.setServiceParent(self.s)

        self.s.startService()
        self._populate_vat_urls()

    def _populate_vat_urls(self):
        node1_url = "http://localhost:%d/messages" % self.node._debug_webport
        node2_url = "http://localhost:%d/messages" % self.node2._debug_webport
        c = self.db.cursor()
        c.execute("INSERT INTO `vat_urls` VALUES (?,?)",
                  (self.server.vatid, node1_url))
        c.execute("INSERT INTO `vat_urls` VALUES (?,?)",
                  (self.server2.vatid, node2_url))
        self.db.commit()
        c = self.db2.cursor()
        c.execute("INSERT INTO `vat_urls` VALUES (?,?)",
                  (self.server.vatid, node1_url))
        c.execute("INSERT INTO `vat_urls` VALUES (?,?)",
                  (self.server2.vatid, node2_url))
        self.db2.commit()

    def tearDown(self):
        return self.s.stopService()
