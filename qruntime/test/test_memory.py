
import json
from twisted.trial import unittest
from .common import ServerBase
from ..memory import create_memory, Memory

class Test(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        self.failUnless(memid.startswith("mem0-"), memid)
        m = Memory(self.db, memid)
        data = m.get_data()
        self.failUnlessEqual(data, {})
        data["hello"] = "world"
        data["subdir"] = {"key": 123}
        packed = json.dumps(data)
        m.save(packed)
        m2 = Memory(self.db, memid)
        self.failUnlessEqual(m2.get_data(),
                             {"hello": "world", "subdir": {"key": 123}})
