
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
        data = json.dumps({"static": {"foo": "bar"},
                           "power": {"__power__": "native", "clid": "1"},
                           "memory": {"__power__": "memory", "clid": "2"},
                           "ref": {"__power__": "reference", "clid": "3"},
                           })
        data_clist = json.dumps({"1": "make_urbject", "2": memid, "3": refid})
        p = pack.unpack_power(t, data, data_clist)
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
        data = json.dumps({"static": {"foo": "bar"},
                           "power": {"__power__": "native", "clid": "1"},
                           "memory": {"__power__": "memory", "clid": "2"},
                           "ref": {"__power__": "reference", "clid": "3"},
                           "sub": {"extra-memory":
                                   {"__power__": "memory", "clid": "2"},
                                   },
                           })
        data_clist = json.dumps({"1": "make_urbject", "2": memid, "3": refid})
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_power, t, data, data_clist)
        self.failUnlessEqual(str(e), "only one Memory per Power")

    def test_bad_unknown_power_type(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "power": {"__power__": "unknown", "clid": "1"},
                           "memory": {"__power__": "memory", "clid": "2"},
                           "ref": {"__power__": "reference", "clid": "3"},
                           })
        data_clist = json.dumps({"1": "make_urbject", "2": memid, "3": refid})
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_power, t, data, data_clist)
        self.failUnlessEqual(str(e), "unknown power type 'unknown'")

class UnpackMemory(_UnpackBase, unittest.TestCase):
    def test_good(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "ref": {"__power__": "reference", "clid": "1"},
                           })
        data_clist = json.dumps({"1": refid})
        p = pack.unpack_memory(t, data, data_clist)
        self.failUnlessEqual(set(p.keys()), set(["static", "ref"]))
        self.failUnlessEqual(p["static"], {"foo": "bar"})
        self.failUnless(isinstance(p["ref"], InnerReference), p["ref"])
        self.failUnlessEqual(t.get_swissnum_for_object(p["ref"]), refid)

    def test_bad_native_in_memory(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "ref": {"__power__": "reference", "clid": "1"},
                           "bad": {"__power__": "native", "clid": "2"},
                           })
        data_clist = json.dumps({"1": refid, "2": "make_urbject"})
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_memory, t, data, data_clist)
        self.failUnlessEqual(str(e), "unknown power type 'native'")

    def test_bad_memory_in_memory(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "ref": {"__power__": "reference", "clid": "1"},
                           "bad": {"__power__": "memory", "clid": "2"},
                           })
        data_clist = json.dumps({"1": refid, "2": memid})
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_memory, t, data, data_clist)
        self.failUnlessEqual(str(e), "only one Memory per Power")
        # TODO: not the best error message

class UnpackArgs(_UnpackBase, unittest.TestCase):
    def test_good(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "ref": {"__power__": "reference", "clid": "1"},
                           })
        data_clist = json.dumps({"1": refid})
        p = pack.unpack_args(t, data, data_clist)
        self.failUnlessEqual(set(p.keys()), set(["static", "ref"]))
        self.failUnlessEqual(p["static"], {"foo": "bar"})
        self.failUnless(isinstance(p["ref"], InnerReference), p["ref"])
        self.failUnlessEqual(t.get_swissnum_for_object(p["ref"]), refid)

    def test_bad_native_in_args(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "ref": {"__power__": "reference", "clid": "1"},
                           "bad": {"__power__": "native", "clid": "2"},
                           })
        data_clist = json.dumps({"1": refid, "2": "make_urbject"})
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_args, t, data, data_clist)
        self.failUnlessEqual(str(e), "unknown power type 'native'")

    def test_bad_memory_in_args(self):
        t, memid, powid, urbjid, refid = self.prepare()
        data = json.dumps({"static": {"foo": "bar"},
                           "ref": {"__power__": "reference", "clid": "1"},
                           "bad": {"__power__": "memory", "clid": "2"},
                           })
        data_clist = json.dumps({"1": refid, "2": memid})
        e = self.failUnlessRaises(ValueError,
                                  pack.unpack_args, t, data, data_clist)
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
        pp = pack.pack_args(t, child)
        power = json.loads(pp.power_json)
        clist = json.loads(pp.power_clist_json)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "clid": 0}})
        self.failUnlessEqual(clist, {"0": list(refid)})

    def test_bad_forged_power(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": {"__power__": "reference", "clid": 0},
                 }
        e = self.failUnlessRaises(ValueError, pack.pack_args, t, child)
        self.failUnlessEqual(str(e), "forbidden __power__ in serializing data")

    def test_good_memory_in_args(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "memory": memory_data, # treated as normal data
                 }
        pp = pack.pack_args(t, child)
        power = json.loads(pp.power_json)
        clist = json.loads(pp.power_clist_json)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "clid": 0},
                                     "memory": {"counter": 0}})
        self.failUnlessEqual(clist, {"0": list(refid)})

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
        pp = pack.pack_memory(t, child)
        power = json.loads(pp.power_json)
        clist = json.loads(pp.power_clist_json)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "clid": 0}})
        self.failUnlessEqual(clist, {"0": list(refid)})

    def test_bad_forged_power(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": {"__power__": "reference", "clid": 0},
                 }
        e = self.failUnlessRaises(ValueError, pack.pack_memory, t, child)
        self.failUnlessEqual(str(e), "forbidden __power__ in serializing data")

    def test_good_memory_in_args(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "memory": memory_data, # treated as normal data
                 }
        pp = pack.pack_memory(t, child)
        power = json.loads(pp.power_json)
        clist = json.loads(pp.power_clist_json)
        self.failUnlessEqual(power, {"static": {"foo": "bar"},
                                     "ref": {"__power__": "reference",
                                             "clid": 0},
                                     "memory": {"counter": 0}})
        self.failUnlessEqual(clist, {"0": list(refid)})

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
        pp = pack.pack_power(t, child)
        power = json.loads(pp.power_json)
        clist = json.loads(pp.power_clist_json)
        self.failUnlessEqual(set(power.keys()),
                             set(["static", "native", "memory", "ref"]))
        self.failUnlessEqual(power["static"],
                             {"foo": "bar", "not-mem": {"counter": 1}})
        n = power["native"]
        self.failUnlessEqual(set(n.keys()), set(["__power__", "clid"]))
        self.failUnlessEqual(n["__power__"], "native")
        self.failUnlessEqual(clist[str(n["clid"])], "make_urbject")
        m = power["memory"]
        self.failUnlessEqual(set(m.keys()), set(["__power__", "clid"]))
        self.failUnlessEqual(m["__power__"], "memory")
        self.failUnlessEqual(clist[str(m["clid"])], memid)
        # pack_power does *not* also pack_memory, so this is 0
        self.failUnlessEqual(Memory(self.db, memid).get_static_data(),
                             {"counter": 0})
        r = power["ref"]
        self.failUnlessEqual(set(r.keys()), set(["__power__", "clid"]))
        self.failUnlessEqual(r["__power__"], "reference")
        self.failUnlessEqual(clist[str(r["clid"])], list(refid))

    def test_good_new_memory(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar", "not-mem": memory_data},
                 "native": native,
                 "memory": {"new-memory": ref},
                 "ref": ref,
                 }
        memory_data["counter"] += 1
        pp = pack.pack_power(t, child)
        power = json.loads(pp.power_json)
        clist = json.loads(pp.power_clist_json)
        self.failUnlessEqual(set(power.keys()),
                             set(["static", "native", "memory", "ref"]))
        self.failUnlessEqual(power["static"],
                             {"foo": "bar", "not-mem": {"counter": 1}})
        n = power["native"]
        self.failUnlessEqual(set(n.keys()), set(["__power__", "clid"]))
        self.failUnlessEqual(n["__power__"], "native")
        self.failUnlessEqual(clist[str(n["clid"])], "make_urbject")

        m = power["memory"]
        self.failUnlessEqual(set(m.keys()), set(["__power__", "clid"]))
        self.failUnlessEqual(m["__power__"], "memory")
        new_memid = clist[str(m["clid"])]
        self.failIfEqual(new_memid, memid)
        mem = Memory(self.db, new_memid)
        self.failUnlessEqual(mem.get_static_data(),
                             {"new-memory": {"__power__": "reference",
                                             "clid": 0}})
        newmem_data = pack.unpack_memory(t, *mem.get_raw_data())
        self.failUnlessEqual(newmem_data, {"new-memory": ref})
        self.failUnlessIdentical(newmem_data["new-memory"], ref)

        r = power["ref"]
        self.failUnlessEqual(set(r.keys()), set(["__power__", "clid"]))
        self.failUnlessEqual(r["__power__"], "reference")
        self.failUnlessEqual(clist[str(r["clid"])], list(refid))

    def test_bad_forged_power(self):
        t, native, memid, memory_data, refid, ref = self.prepare()
        child = {"static": {"foo": "bar"},
                 "ref": ref,
                 "bad": {"__power__": "reference", "clid": 0},
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
