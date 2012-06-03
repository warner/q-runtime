
import os, json, copy
from twisted.python import log
from . import util
from .memory import Memory

def create_urbject(db, powid, code):
    urbjid = util.to_ascii(os.urandom(32), "urb0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `urbjects` VALUES (?,?,?)", (urbjid, powid, code))
    db.commit()
    return urbjid

def create_power(db, packed_power):
    powid = util.to_ascii(os.urandom(32), "pow0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `power` VALUES (?,?,?)",
              (powid, packed_power.power_json,
               packed_power.power_clist_json))
    db.commit()
    return powid

class CList(dict):
    def add(self, value):
        key = len(self)
        self[key] = value
        return key

def create_power_for_memid(db, memid=None, grant_make_urbject=False):
    powid = util.to_ascii(os.urandom(32), "pow0-", encoding="base32")
    power = {}
    power_clist = CList()
    if memid:
        power["memory"] = {"__power__": "memory",
                           "clid": power_clist.add(memid)}
    if grant_make_urbject:
        power["make_urbject"] = {"__power__": "native",
                                 "clid": power_clist.add("make_urbject")}
    c = db.cursor()
    c.execute("INSERT INTO `power` VALUES (?,?,?)",
              (powid, json.dumps(power), json.dumps(power_clist)))
    db.commit()
    return powid

# the inner (sandboxed) code gets a power= argument which contains static
# data, Memory-backed dicts (which behave just like static data but can be
# detected and serialized), and InnerReference objects (which remember a
# .clid and have an invoke() method).

# This is created from a power_json/clist_json pair, in which power_json
# represents Memory objects with {__power__:"memory",clid=clid}, and
# InnerReference objects with {__power__:"reference",clid=clid}. clist_json
# maps clid to memid or urbjid

# To track these, the outer code retains a clist that maps from clid to
# urbjid (for InnerReferences), and a table that maps from the id() of the
# Memory-backed dicts to (memid, Memory).

# when serializing (packing) a power= argument from the inner code, we do
# JSON serialization, but catch memory-backed dicts by looking for their id
# in the table, and catch InnerReferences with isinstance().

class InnerReference:
    def __init__(self, clid):
        self.clid = clid
    def invoke(self, args):
        NotImplementedError

class NativePower:
    def __init__(self, f, clid):
        self.f = f
        self.clid = clid
    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)


class Invocation:
    def __init__(self, db, urb):
        self.db = db
        self.urb = urb

        self.code, powid = urb.get_code_and_powid()
        self.clist = CList()
        up = Unpacking(self.db, self.clist)
        self.outer_power = up.unpack_power(*get_power(self.db, powid))

    def invoke_static(self, static_args, from_vatid, debug=None):
        return self.execute(static_args, from_vatid, debug=None)

    def invoke(self, packed_args, from_vatid, debug=None):
        up = Unpacking(self.db, self.clist)
        inner_args = up.unpack_args(packed_args.power_json,
                                    packed_args.power_clist_json)
        return self.execute(inner_args, from_vatid, debug)

    def execute(self, db, args, from_vatid, debug=None):
        log.msg("EVAL <%s>" % (self.code,))
        log.msg("ARGS <%s>" % (args,))
        code = compile(self.code, "<from vatid %s>" % from_vatid, "exec")
        inner_power = self.outer_power.inner_power
        # save contents even if they trash 'power.memory'
        memory = self.outer_power.memory
        memory_contents = inner_power.get("memory")
        def log2(msg):
            log.msg(msg)
            print msg
        namespace = {"log": log2, "add": add}
        if debug:
            namespace["debug"] = debug

        eval(code, namespace, namespace)
        rc = namespace["call"](args, inner_power)
        del rc # rc is dropped for now

        if memory:
            p = Packing(self.db, self.outer_power)
            memory.save(p.pack_memory(memory_contents))

        

class PackedPower:
    def __init__(self, power_json, power_clist_json):
        # power_json is a string with the encoded child-visible power= object
        self.power_json = power_json
        # power_clist_json is a string with the encoded clist, that maps from
        # the power= object's clids to actual swissnums (memids and urbjids)
        self.power_clist_json = power_clist_json

class PowerEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, NativePower) and self._power_allow_native:
            old_clid = obj.clid
            name = self._power_old_clist[old_clid]
            new_clid = self._power_new_clist.add(name)
            return {"__power__": "native", "clid": new_clid}
        if isinstance(obj, InnerReference):
            old_clid = obj.clid
            urbjid = self._power_old_clist[old_clid]
            new_clid = self._power_new_clist.add(urbjid)
            return {"__power__": "reference", "clid": new_clid}
        return json.JSONEncoder.default(self, obj)

class Packing:
    def __init__(self, db, outer_power):
        self.db = db
        self.outer_power = outer_power
        self.clist = CList()
        self._used = False

    # choose exactly one of these three entry points
    def pack_power(self, child_power):
        # used for make_object(code, power). Can serialize static, References,
        # NativePowers, and one memory.
        assert not self._used
        self._used = True
        return self._pack(child_power, True, True)

    def pack_memory(self, inner_memory):
        # Can serialize static, References, NativePowers, but not Memory.
        assert not self._used
        self._used = True
        return self._pack(inner_memory, True, False)

    def pack_args(self, child_args):
        # Can serialize static and References, but not NativePowers or Memory
        assert not self._used
        self._used = True
        return self._pack(child_args, False, False)

    def _pack_memory(self, inner_memory):
        # This lets pack_power() one-time-recursively pack power.memory and
        # have both _power and _memory add to the same clist
        assert self._used
        return self._pack(inner_memory, True, False)

    def _build_fake_memory(self, old_memory):
        if old_memory is self.outer_power.memory:
            # the child will share the parent's Memory
            new_clid = self.clist.add(self.outer_power.memory.memid)
            return {"__power__": "memory", "clid": new_clid}

        # the child gets a new Memory with some initial contents
        packed = self._pack_memory(old_memory)
        memid = memory.create_memory(self.db, packed.contents, packed.clist)
        new_clid = self.clist.add(memid)
        return  {"__power__": "memory", "clid": new_clid}

    def _pack(self, child_power, allow_native, allow_memory):
        if allow_memory:
            # we handle a top-level Memory object by pretending that the
            # original data contains a {__power__:memory} dict. We must
            # modify a copy, not the original.
            child_power, old_child_power = {}, child_power
            for k in old_child_power: # shallow copy
                if k == "memory":
                    old_memory = old_child_power[k]
                    if old_memory is not None:
                        child_power[k] = self._build_fake_memory(old_memory)
                else:
                    child_power[k] = old_child_power[k]

        enc = PowerEncoder()
        enc._power_allow_native = allow_native
        enc._power_old_clist = self.outer_power.clist
        enc._power_new_clist = self.clist
        new_power_json = enc.encode(child_power)
        packed = PackedPower(new_power_json, json.dumps(new_clist))
        return packed

class OuterPower:
    """This is held outside the sandbox, and maps inside-sandbox placeholders
    to the real powers."""
    memory = None

    def fill(self, inner_power, clist):
        # inner_power is the dictionary passed to sandboxed code as power=
        self.inner_power = inner_power
        # .clist maps clids from .inner_power objects to real swissnums
        self.clist = clist

    def set_memory(self, memory):
        # .memory remembers the Memory object that was in power.memory . Can
        # be None if this child was not given any memory.
        assert not self.memory, "only one Memory per Power"
        self.memory = memory

class Unpacking:
    def __init__(self, db, clist):
        self.db = db
        self.clist = clist # maps clids to swissnums
        self.outer_power = OuterPower()
        self._used = False

    # choose exactly one of these three entry points
    def unpack_power(self, power_json, clist_json):
        self._call_once()
        inner_power = self._unpack(power_json, clist_json, True, True)
        return self._return_outer_power(inner_power)

    def unpack_memory(self, power_json, clist_json):
        self._call_once()
        inner_power = self._unpack(power_json, clist_json, True, False)
        return self._return_outer_power(inner_power)

    def unpack_args(self, power_json, clist_json):
        self._call_once()
        inner_power = self._unpack(power_json, clist_json, False, False)
        return self._return_outer_power(inner_power)

    def _call_once(self):
        assert not self._used
        self._used = True

    def _return_outer_power(self, inner_power):
        self.outer_power.fill(inner_power, self.clist)
        return self.outer_power

    def _unpack_memory(self, power_json, clist_json):
        assert self._used
        return self._unpack(power_json, clist_json, True, False)

    def _unpack(self, power_json, clist_json, allow_native, allow_memory):
        # create the inner power object, and the clist, and the memorylist
        def inner_make_urbject(code, child_power):
            packed_power = pack_power(child_power, self.outer_power)
            powid = create_power(db, packed_power)
            urbjid = create_urbject(db, powid, code)
            # this will update Invocation.clist, adding new powers (for the
            # newly created object)
            clid = self.outer_power.clist.add(urbjid)
            return InnerReference(clid)

        old_clist = json.loads(clist_json)
        def hook(dct):
            if "__power__" in dct:
                ptype = dct["__power__"]
                old_clid = str(dct["clid"]) # points into old_clist
                # str because 'clist' keys (like all JSON keys) are strings
                if ptype == "native" and allow_native:
                    name = old_clist[old_clid]
                    if name == "make_urbject":
                        return NativePower(inner_make_urbject,
                                           self.clist.add(name))
                    raise ValueError("unknown native power %s" % (name,))
                if ptype == "memory" and allow_memory:
                    memid = old_clist[old_clid]
                    # memid doesn't live in the new clist, just in
                    # OuterPower.memory.memid
                    memory = Memory(db, memid)
                    self.outer_power.set_memory(memory) # set-once
                    # now extract the contents
                    memory_json, memory_clist_json = memory.get_raw_data()
                    # unpack_memory() can add items to our clist: the
                    # invocation gets power from Memory as well as args
                    data = self._unpack_memory(memory_json, memory_clist_json)
                    return data
                if ptype == "reference":
                    r = InnerReference(self.clist.add(old_clist[clid]))
                    return r
                raise ValueError("unknown power type %s" % (ptype,))
            return dct
        try:
            inner_power = json.loads(power_json, object_hook=hook)
        except:
            print "unpack_power exception, power_json='%s'" % power_json
            raise
        return inner_power


def get_power(db, powid):
    c = db.cursor()
    c.execute("SELECT `power_json`,`power_clist_json` FROM `power`"
              " WHERE `powid`=?", (powid,))
    results = c.fetchall()
    assert results, "no powid %s" % powid
    (power_json, power_clist_json) = results[0]
    return (power_json, power_clist_json)


def add(a, b):
    c = copy.deepcopy(a)
    for key in b:
        c[key] = b[key]
    return c




class Urbject:
    def __init__(self, db, urbjid):
        self.db = db
        self.urbjid = urbjid

    def invoke_static(self, args, from_vatid, debug=None):
        i = Invocation(self.db, self)
        # args= are static for now: nothing magic
        return i.invoke_static(args, from_vatid, debug)

    def invoke(self, packed_args, from_vatid, debug=None):
        i = Invocation(self.db, self)
        return i.invoke(packed_args, from_vatid, debug)

    def get_code_and_powid(self):
        c = self.db.cursor()
        print "URBJID", self.urbjid
        c.execute("SELECT `code`,`powid` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        code, powid = res[0]
        return code, powid
