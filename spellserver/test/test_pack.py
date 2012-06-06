
import re, json
from twisted.trial import unittest
from .common import ServerBase
from ..common import NativePower, InnerReference
from ..memory import create_memory, Memory
from ..urbject import create_urbject, create_power_for_memid
from ..turn import Turn
from .. import pack

class _UnpackBase(ServerBase):
    def prepare(self):
        t = Turn(self.server, self.db)
        memid = create_memory(self.db, {"counter": 0})
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, "code")
        refid = ("vatid", urbjid)
        return t, memid, powid, urbjid, refid

class UnpackPower(_UnpackBase, unittest.TestCase):
    def test_good(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "power": {"__power__": "native", "swissnum": "make_urbject"},
                "memory": {"__power__": "memory", "swissnum": memid},
                "ref": {"__power__": "reference", "swissnum": refid},
                }
        p = pack.unpack_power(t, json.dumps(data))
        self.failUnlessEqual(set(p.keys()),
                             set(["static", "power", "memory", "ref"]))
        self.failUnlessEqual(p["static"], {"foo": "bar"})
        self.failUnlessEqual(p["memory"], {"counter": 0})
        self.failUnless(id(p["memory"]) in t.memory_data_to_memid)
        self.failUnlessEqual(t.memory_data_to_memid[id(p["memory"])], memid)
        self.failUnless(isinstance(p["power"], NativePower), p["power"])
        self.failUnlessEqual(t.get_swissnum_for_object(p["power"]), "make_urbject")
        self.failUnless(isinstance(p["ref"], InnerReference), p["ref"])
        self.failUnlessEqual(t.get_swissnum_for_object(p["ref"]), refid)

    def test_bad_only_one_memory(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "power": {"__power__": "native", "swissnum": "make_urbject"},
                "memory": {"__power__": "memory", "swissnum": memid},
                "ref": {"__power__": "reference", "swissnum": refid},
                "sub": {"extra-memory":
                        {"__power__": "memory", "swissnum": memid},
                        },
                }
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_power, t, json.dumps(data))
        self.failUnlessEqual(str(e), "only one Memory per Power")

    def test_bad_unknown_power_type(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "power": {"__power__": "unknown", "swissnum": "make_urbject"},
                "memory": {"__power__": "memory", "swissnum": memid},
                "ref": {"__power__": "reference", "swissnum": refid},
                }
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_power, t, json.dumps(data))
        self.failUnlessEqual(str(e), "unknown power type 'unknown'")

class UnpackMemory(_UnpackBase, unittest.TestCase):
    def test_good(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "ref": {"__power__": "reference", "swissnum": refid},
                }
        p = pack.unpack_memory(t, json.dumps(data))
        self.failUnlessEqual(set(p.keys()), set(["static", "ref"]))
        self.failUnlessEqual(p["static"], {"foo": "bar"})
        self.failUnless(isinstance(p["ref"], InnerReference), p["ref"])
        self.failUnlessEqual(t.get_swissnum_for_object(p["ref"]), refid)

    def test_bad_native_in_memory(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "ref": {"__power__": "reference", "swissnum": refid},
                "bad": {"__power__": "native", "swissnum": "make_urbject"},
                }
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_memory, t, json.dumps(data))
        self.failUnlessEqual(str(e), "unknown power type 'native'")

    def test_bad_memory_in_memory(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "ref": {"__power__": "reference", "swissnum": refid},
                "bad": {"__power__": "memory", "swissnum": memid},
                }
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_memory, t, json.dumps(data))
        self.failUnlessEqual(str(e), "only one Memory per Power")
        # TODO: not the best error message

class UnpackArgs(_UnpackBase, unittest.TestCase):
    def test_good(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "ref": {"__power__": "reference", "swissnum": refid},
                }
        p = pack.unpack_args(t, json.dumps(data))
        self.failUnlessEqual(set(p.keys()), set(["static", "ref"]))
        self.failUnlessEqual(p["static"], {"foo": "bar"})
        self.failUnless(isinstance(p["ref"], InnerReference), p["ref"])
        self.failUnlessEqual(t.get_swissnum_for_object(p["ref"]), refid)

    def test_bad_native_in_args(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "ref": {"__power__": "reference", "swissnum": refid},
                "bad": {"__power__": "native", "swissnum": "make_urbject"},
                }
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_args, t, json.dumps(data))
        self.failUnlessEqual(str(e), "unknown power type 'native'")

    def test_bad_memory_in_args(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = {"static": {"foo": "bar"},
                "ref": {"__power__": "reference", "swissnum": refid},
                "bad": {"__power__": "memory", "swissnum": memid},
                }
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_args, t, json.dumps(data))
        self.failUnlessEqual(str(e), "only one Memory per Power")
        # TODO: not the best error message

class _PackBase(ServerBase):
    def prepare(self):
        t = Turn(self.server, self.db)
        native = t.get_native_power("make_urbject")
        memid = create_memory(self.db, {"counter": 0})
        memory_data = t.get_memory(memid)
        powid = create_power_for_memid(self.db, memid)
        urbjid = create_urbject(self.db, powid, "code")
        refid = ("vatid", urbjid)
        ref = t.get_reference(refid)
        return t, native, memid, memory_data, refid, ref

class PackArgs(_PackBase, unittest.TestCase):
    def test_good(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 }
        packed = pack.pack_args(t, child)
        power = json.loads(packed)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "swissnum": list(refid)}})

    def test_bad_forged_power(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": {"__power__": "reference", "swissnum": 0},
                 }
        e = self.failUnlessRaises(ValueError, pack.pack_args, t, child)
        self.failUnlessEqual(str(e), "forbidden __power__ in serializing data")

    def test_good_memory_in_args(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "memory": memory_data, # treated as normal data
                 }
        packed = pack.pack_args(t, child)
        power = json.loads(packed)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "swissnum": list(refid)},
                                     "memory": {"counter": 0}})

    def test_bad_native_in_args(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": native,
                 }
        e = self.failUnlessRaises(TypeError, pack.pack_args, t, child)
        exp = r'NativePower instance at \w+> is not JSON serializable'
        self.failUnless(re.search(exp, str(e)), str(e))

class PackMemory(_PackBase, unittest.TestCase):
    def test_good(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 }
        packed = pack.pack_memory(t, child)
        power = json.loads(packed)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "swissnum": list(refid)}})

    def test_bad_forged_power(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": {"__power__": "reference", "swissnum": 0},
                 }
        e = self.failUnlessRaises(ValueError, pack.pack_memory, t, child)
        self.failUnlessEqual(str(e), "forbidden __power__ in serializing data")

    def test_good_memory_in_args(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "memory": memory_data, # treated as normal data
                 }
        packed = pack.pack_memory(t, child)
        power = json.loads(packed)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "swissnum": list(refid)},
                                     "memory": {"counter": 0}})

    def test_bad_native_in_args(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": native,
                 }
        e = self.failUnlessRaises(TypeError, pack.pack_memory, t, child)
        exp = r'NativePower instance at \w+> is not JSON serializable'
        self.failUnless(re.search(exp, str(e)), str(e))

class PackPower(_PackBase, unittest.TestCase):
    def test_good_old_memory(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar", "not-mem": memory_data},
                 "native": native,
                 "memory": memory_data,
                 "ref": ref,
                 }
        memory_data["counter"] += 1 # pack_power does *not* also pack_memory
        packed = pack.pack_power(t, child)
        power = json.loads(packed)
        self.failUnlessEqual(power,
                             {"static": {"foo": "bar",
                                         "not-mem": {"counter": 1}},
                              "native": {"__power__": "native",
                                         "swissnum": "make_urbject"},
                              "memory": {"__power__": "memory",
                                         "swissnum": memid},
                              "ref": {"__power__": "reference",
                                      "swissnum": list(refid)},
                              })
        # pack_power does *not* also pack_memory, so this is 0
        self.failUnlessEqual(Memory(self.db, memid).get_data(), {"counter": 0})

    def test_good_new_memory(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar", "not-mem": memory_data},
                 "native": native,
                 "memory": {"new-memory": ref},
                 "ref": ref,
                 }
        memory_data["counter"] += 1
        packed = pack.pack_power(t, child)
        power = json.loads(packed)
        new_memid = power["memory"]["swissnum"]
        self.failIfEqual(new_memid, memid)
        self.failUnlessEqual(power,
                             {"static": {"foo": "bar",
                                         "not-mem": {"counter": 1}},
                              "native": {"__power__": "native",
                                         "swissnum": "make_urbject"},
                              "memory": {"__power__": "memory",
                                         "swissnum": new_memid},
                              "ref": {"__power__": "reference",
                                      "swissnum": list(refid)},
                              })
        mem = Memory(self.db, new_memid)
        self.failUnlessEqual(mem.get_data(),
                             {"new-memory": {"__power__": "reference",
                                             "swissnum": list(refid)}})
        newmem_data = pack.unpack_memory(t, mem.get_raw_data())
        self.failUnlessEqual(newmem_data, {"new-memory": ref})
        self.failUnlessIdentical(newmem_data["new-memory"], ref)


    def test_bad_forged_power(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": {"__power__": "reference", "swissnum": list(refid)},
                 }
        e = self.failUnlessRaises(ValueError, pack.pack_power, t, child)
        self.failUnlessEqual(str(e), "forbidden __power__ in serializing data")

    def OFF_test_bad_native_below_top_level(self):
        # this isn't actually forbidden yet, but I might change my mind
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "memory": memory_data,
                 "sub": {"bad": native},
                 }
        e = self.failUnlessRaises(ValueError, pack.pack_power, t, child)
        self.failUnlessEqual(str(e), "forbidden NativePower below top-level")
