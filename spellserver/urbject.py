
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

class OuterPower:
    """This is held outside the sandbox, and maps inside-sandbox placeholders
    to the real powers."""
    def fill(self, inner_power, clist, memory):
        # inner_power is the dictionary passed to sandboxed code as power=
        self.inner_power = inner_power
        # .clist maps clids from .inner_power objects to real swissnums
        self.clist = clist
        # .memory remembers the Memory object that was in power.memory . Can
        # be None if this child was not given any memory.
        self.memory = memory

def unpack_power(db, power_json, clist_json):
    return unpack(db, power_json, clist_json, True, True, None)
def unpack_memory(db, power_json, clist_json, new_clist):
    return unpack(db, power_json, clist_json, True, False, new_clist)
def unpack_args(db, power_json, clist_json, new_clist):
    return unpack(db, power_json, clist_json, False, False, new_clist)

def unpack(db, power_json, clist_json, allow_native, allow_memory, new_clist):
    # create the inner power object, and the clist, and the memorylist
    outer_power = OuterPower()
    def inner_make_urbject(code, child_power):
        packed_power = pack_power(child_power, outer_power)
        powid = create_power(db, packed_power)
        urbjid = create_urbject(db, powid, code)
        clid = outer_power.clist.add(urbjid)
        return InnerReference(clid)
    if new_clist is None:
        # unpack_memory() needs to provide its own new_clist so the newly
        # unpacked objects can be allocated clids properly. Likewise
        # unpack_args() provides the clist from the unpack_power() call that
        # just preceded it.
        new_clist = CList() # maps clids to swissnums
    old_clist = json.loads(clist_json)
    memory = None

    def hook(dct):
        if "__power__" in dct:
            ptype = dct["__power__"]
            old_clid = str(dct["clid"]) # points into old_clist
            # str because 'clist' keys (like all JSON keys) are strings
            if ptype == "native" and allow_native:
                name = old_clist[old_clid]
                if name == "make_urbject":
                    return NativePower(inner_make_urbject, new_clist.add(name))
                raise ValueError("unknown native power %s" % (name,))
            if ptype == "memory" and allow_memory:
                assert not memory, "only one Memory per Power"
                memid = old_clist[old_clid]
                # memid doesn't live in new_clist, just in OuterPower.memory
                memory = Memory(db, memid)
                memory_json, memory_clist_json = memory.get_raw_data()
                # unpack_memory() also adds itens to new_clist
                data = unpack_memory(db, memory_json, memory_clist_json,
                                     new_clist).inner_power
                return data
            if ptype == "reference":
                r = InnerReference(new_clist.add(old_clist[clid]))
                return r
            raise ValueError("unknown power type %s" % (ptype,))
        return dct
    try:
        inner_power = json.loads(power_json, object_hook=hook)
    except:
        print "unpack_power exception, power_json='%s'" % power_json
        raise
    outer_power.fill(inner_power, new_clist, memory)
    return outer_power

def get_power(db, powid):
    c = db.cursor()
    c.execute("SELECT `power_json`,`power_clist_json` FROM `power`"
              " WHERE `powid`=?", (powid,))
    results = c.fetchall()
    assert results, "no powid %s" % powid
    (power_json, power_clist_json) = results[0]
    return unpack_power(db, power_json, power_clist_json)


def add(a, b):
    c = copy.deepcopy(a)
    for key in b:
        c[key] = b[key]
    return c

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

def pack_power(db, child_power, outer_power):
    # used for make_object(code, power). Can serialize static, References,
    # NativePowers, and one memory.
    return pack(db, child_power, outer_power, True, True)
def pack_memory(db, inner_memory, outer_power):
    # Can serialize static, References, NativePowers, but not Memory.
    return pack(db, inner_memory, outer_power, True, False)
def pack_args(db, child_args, outer_power):
    # Can serialize static and References, but not NativePowers or Memory
    return pack(db, child_args, outer_power, False, False)

def pack(db, child_power, outer_power, allow_native, allow_memory):
    if allow_memory:
        # we handle a top-level Memory object by pretending that the original
        # data contains a {__power__:memory} dict. We must modify a copy, not
        # the original.
        child_power, old_child_power = {}, child_power
        child_clist = CList(outer_power.clist) # copy
        for k in old_child_power: # shallow copy
            if k != "memory":
                child_power[k] = old_child_power[k]
        if old_child_power.get("memory") is not None:
            if old_child_power["memory"] is outer_power.memory:
                # the child will share the parent's Memory
                new_clid = child_clist.add(outer_power.memory.memid)
                child_power["memory"] = {"__power__": "memory",
                                         "clid": new_clid}
            else:
                # the child gets a new Memory with some initial contents
                initial_contents = old_child_power["memory"]
                packed = pack_memory(db, initial_contents, outer_power)
                memid = memory.create_memory(db, packed.contents, packed.clist)
                new_clid = child_clist.add(memid)
                child_power["memory"] = {"__power__": "memory",
                                         "clid": new_clid}
    else:
        child_clist = outer_power.clist

    enc = PowerEncoder()
    enc._power_allow_native = allow_native
    enc._power_old_clist = child_clist
    enc._power_new_clist = new_clist = CList()
    new_power_json = enc.encode(child_power)
    packed = PackedPower(new_power_json, json.dumps(new_clist))
    return packed


def execute(db, code, args, outer_power, from_vatid, debug=None):
    log.msg("EVAL <%s>" % (code,))
    log.msg("ARGS <%s>" % (args,))
    code = compile(code, "<from vatid %s>" % from_vatid, "exec")
    memory = outer_power.memory # save contents even if they trash 'power'
    def log2(msg):
        log.msg(msg)
        print msg
    namespace = {"log": log2, "add": add}
    if debug:
        namespace["debug"] = debug

    eval(code, namespace, namespace)
    rc = namespace["call"](args, outer_power.inner_power)
    del rc # rc is dropped for now

    if memory:
        memory.save(pack_memory(db, memory.data, outer_power))



class Urbject:
    def __init__(self, db, urbjid):
        self.db = db
        self.urbjid = urbjid

    def invoke(self, args, from_vatid, debug=None):
        # args= are static for now: nothing magic
        code, powid = self.get_code_and_powid()
        outer_power = get_power(self.db, powid)
        return execute(self.db, code, args, outer_power, from_vatid, debug)

    def invoke2(self, packed_args, from_vatid, debug=None):
        code, powid = self.get_code_and_powid()
        outer_power = get_power(self.db, powid)
        outer_args = unpack_args(self.db, packed_args.power_json,
                                 packed_args.power_clist_json,
                                 outer_power.clist)
        return execute(self.db, code,
                       outer_args.inner_power, outer_power,
                       from_vatid, debug)

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
