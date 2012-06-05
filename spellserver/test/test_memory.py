
import json
from twisted.trial import unittest
from .common import ServerBase
from ..memory import create_memory, Memory
from ..pack import PackedPower

class Test(ServerBase, unittest.TestCase):

    def test_basic(self):
        memid = create_memory(self.db)
        self.failUnless(memid.startswith("mem0-"), memid)
        m = Memory(self.db, memid)
        data = m.get_static_data()
        self.failUnlessEqual(data, {})
        data["hello"] = "world"
        data["subdir"] = {"key": 123}
        packed = PackedPower(json.dumps(data), json.dumps({}))
        m.save(packed)
        m2 = Memory(self.db, memid)
        self.failUnlessEqual(m2.get_static_data(),
                             {"hello": "world", "subdir": {"key": 123}})
