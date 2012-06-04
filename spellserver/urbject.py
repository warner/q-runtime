
import os, json, copy, weakref
from twisted.python import log
from . import util
from .memory import Memory, create_raw_memory

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
    def __init__(self, turn):
        self._turn = turn
    def send(self, args):
        return self._turn.outbound_message(self, args)
    def call(self, args):
        return self._turn.local_sync_call(self, args)

class NativePower:
    def __init__(self, f):
        self.f = f
    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)

def inner_add(a, b):
    c = copy.copy(a) # shallow. We want p=add(power, stuff) to retain the
                     # object identity of "p.memory is power.memory"
    for key in b:
        c[key] = b[key]
    return c



class Turn:
    """This holds all the state for a single turn of the vat."""
    def __init__(self, server, db):
        self._server = server
        self._vatid = server.vatid
        self.db = db

        self.ALL_NATIVE_POWERS = {"make_urbject": inner_make_urbject}

        # self.swissnums maps from an object (NativePower or InnerReference)
        # to swissnum, via a WeakKeyDictionary. This lets us avoid allocating
        # clids just for OuterPower. There is one .swissnums shared for all
        # stack frames of the turn.
        if swissnums is None:
            swissnums = weakref.WeakKeyDictionary()
        self.swissnums = swissnums

        self.native_powers = {} # name to NativePower object

        # self.memories maps from a memid to a (Memory, data) pair. This
        # makes sure that sub-invocations (via o.call) get the same data as
        # the parent, and that their modifications are immediately visible to
        # the parent. There is one .memories shared for all stack frames of
        # the turn.
        if memories is None:
            memories = {}
        self.memories = memories

    def outbound_message(self, inner_ref, args):
        packed_args = Packing(self.db, self).pack_args(args)
        # local-only for now
        target_vatid, target_urbjid = self.swissnums[inner_ref]
        msg = {"command": "invoke",
               "urbjid": target_urbjid,
               "args_json": packed_args.power_json,
               "args_clist_json": packed_args.power_clist_json}
        self._server.send_message(target_vatid, json.dumps(msg))
        return None # no results-Promises yet

    def get_power(self, powid):
        if powid not in self.powers:
            c = self.db.cursor()
            c.execute("SELECT `power_json`,`power_clist_json` FROM `power`"
                      " WHERE `powid`=?", (powid,))
            results = c.fetchall()
            assert results, "no powid %s" % powid
            (power_json, power_clist_json) = results[0]
            inner = unpack_power(self, power_json, power_clist_json)
            self.powid_to_power[powid] = inner
            self.power_to_powid[inner] = powid
        return self.powid_to_power[powid]

    def inner_make_urbject(self, code, child_power):
        """Create a make_urbject() function for the inner code."""
        # When called later, the packer will need to pull swissnums from the
        # Turn, and compare both .power and .memory to see if we're sharing
        # power or memory with the child
        if child_power in self.power_to_powid:
            # reuse the existing powid instead of creating a new one
            powid = self.power_to_powid[child_power]
        else:
            p = Packing(self.db, self)
            packed_power = p.pack_power(child_power)
            powid = create_power(self.db, packed_power)
        urbjid = create_urbject(self.db, powid, code)
        # this will update Invocation.swissnums, so it will have the
        # ability to serialize the newly created object at the end of the
        # turn
        ir = InnerReference(self.turn)
        self.turn.add_local_urbject(ir, urbjid)
        return ir

    def get_native_power(self, name):
        if name not in self.native_powers:
            if name not in self.ALL_NATIVE_POWERS:
                raise ValueError("unknown native power %s" % (name,))
            f = self.ALL_NATIVE_POWERS[name]
            o = NativePower(f)
            self.native_powers[name] = o
            self.swissnums[o] = name
        return self.native_powers[name]

    def get_memory(self, memid):
        if memid not in self.memories:
            memory = Memory(self.db, memid)
            # now extract the contents
            # unpack_memory() can add items to our swissnums: the
            # invocation gets power from Memory as well as args
            memory_json, memory_clist_json = memory.get_raw_data()
            data = unpack_memory(self, memory_json, memory_clist_json)
            self.memories[memid] = (memory, data)
        (memory, data) = self.memories[memid]
        return data

    def get_reference(self, refid):
        if refid not in self.references:
            r = InnerReference(self)
            self.references[refid] = r
            self.swissnums[r] = refid
        return self.references[refid]

    def add_local_urbject(self, inner_ref, urbjid):
        assert self._vatid
        self.swissnums[inner_ref] = (self._vatid, urbjid)

    def commit_turn(self):
        for (memid, (memory, data)) in self.memories.items():
            p = Packing(self.db, self)
            memory.save(p.pack_memory(data))


    def start_turn(self, code, powid, args_json, args_clist_json, from_vatid,
                   debug=None):
        first_i = Invocation(self, code, powid)
        rc = first_i.invoke(args_json, args_clist_json, from_vatid, debug)
        return rc

    def local_sync_call(self, inner_ref, args):
        target_vatid, target_urbjid = self.swissnums[inner_ref]
        assert target_vatid == self._vatid # must be local
        ur = Urbject(self._server, self.db, target_urbjid)
        code, powid = ur.get_code_and_powid()
        rc = Invocation(self, code, powid)._execute(args, self._vatid)
        return rc

class Invocation:
    def __init__(self, turn, code, powid):
        self.code = code
        self.turn = turn

        # self.memory holds the Memory object used for this one stack frame
        # (invocation of a specific urbjid) whose contents populates
        # power.memory, and self.memory_data holds the actual power.memory
        # dictionary itself (used for object comparison in make_urbject() to
        # tell if the power.memory being handed to the child is the same as
        # our own, and thus should be shared). Both can be None if this child
        # was not given any memory
        self.memory = XXX
        self.memory_data = XXX

        # self.inner_power holds the 'power' dictionary for the same frame,
        # passed to sandboxed code as power=
        self.inner_power = turn.get_power(powid)

    def _invoke(self, args_json, args_clist_json, from_vatid, debug=None):
        inner_args = unpack_args(self.turn, args_json, args_clist_json)
        return self._execute(inner_args, from_vatid, debug)

    def _execute(self, args, from_vatid, debug=None):
        #print "EVAL <%s>" % (self.code,)
        #print " ARGS <%s>" % (args,)
        code = compile(self.code, "<from vatid %s>" % from_vatid, "exec")
        def log2(msg):
            log.msg(msg)
            #print msg
        namespace = {"log": log2, "add": inner_add}
        if debug:
            namespace["debug"] = debug

        eval(code, namespace, namespace)
        rc = namespace["call"](args, self.inner_power)

        return rc # only used by local_sync_call for now

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
            name = self._power_old_swissnums[obj]
            new_clid = self._power_new_clist.add(name)
            return {"__power__": "native", "clid": new_clid}
        if isinstance(obj, InnerReference):
            refid = self._power_old_swissnums[obj]
            new_clid = self._power_new_clist.add(refid)
            return {"__power__": "reference", "clid": new_clid}
        return json.JSONEncoder.default(self, obj)

class Packing:
    def __init__(self, db, invocation):
        self.db = db
        self.invocation = invocation
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
        # XXX this will need to insert different objects in our copy, because
        # the confined code must be prohibited from inserting these same
        # objects to violate confinement (our encoder needs to reject
        # '__power__' properties from the inner code). The use of 'clid'
        # prevents them from gaining any new powers, but in the future we'll
        # probably change this to use swissnums directly, at which point
        # it'll become pretty important.
        if old_memory is self.outer_power.memory_data:
            # the child will share the parent's Memory
            new_clid = self.clist.add(self.outer_power.memory.memid)
            return {"__power__": "memory", "clid": new_clid}

        # the child gets a new Memory with some initial contents
        packed = self._pack_memory(old_memory)
        memid = create_raw_memory(self.db, packed.power_json,
                                  packed.power_clist_json)
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
        enc._power_old_swissnums = self.invocation.swissnums
        enc._power_new_clist = self.clist
        new_power_json = enc.encode(child_power)
        packed = PackedPower(new_power_json, json.dumps(self.clist))
        return packed

class Unpacking:
    def __init__(self, turn, allow_native, allow_memory):
        self.turn = turn
        self._allow_native = allow_native
        self._allow_memory = allow_memory

    def unpack(self, power_json, clist_json):
        # create the inner object. Adds anything necessary to the Turn
        old_clist = json.loads(clist_json)
        def hook(dct):
            if "__power__" not in dct:
                return dct
            ptype = dct["__power__"]
            old_clid = str(dct["clid"]) # points into old_clist
            # str because 'clist' keys (like all JSON keys) are strings
            if ptype == "native" and self._allow_native:
                name = old_clist[old_clid]
                return self.turn.get_native_power(name)
            if ptype == "memory":
                if not self._allow_memory:
                    raise ValueError("only one Memory per Power")
                self._allow_memory = False
                memid = old_clist[old_clid]
                return self.turn.get_memory(memid) # data
            if ptype == "reference":
                refid = old_clist[old_clid]
                return self.turn.get_reference(refid) # InnerReference
            raise ValueError("unknown power type %s" % (ptype,))
        try:
            unpacked = json.loads(power_json, object_hook=hook)
        except:
            print "unpack_power exception, power_json='%s'" % power_json
            raise
        return unpacked

def unpack_power(turn, power_json, clist_json):
    # updates turn.swissnums, turn.native_powers, and turn.memories . Returns
    # inner_power.
    up = Unpacking(turn, allow_native=True, allow_memory=True)
    return up.unpack(power_json, clist_json)

def unpack_memory(turn, power_json, clist_json):
    # updates turn.swissnums . Returns data. You need to update turn.memories
    up = Unpacking(turn, allow_native=False, allow_memory=False)
    return up_unpack(power_json, clist_json)

def unpack_args(turn, power_json, clist_json):
    # updates turn.swissnums . Returns inner_power.
    up = Unpacking(turn, allow_native=False, allow_memory=False)
    return up.unpack(power_json, clist_json)



class Urbject:
    def __init__(self, server, db, urbjid):
        self._server = server
        self.db = db
        self.urbjid = urbjid

    def invoke(self, args, args_clist, from_vatid, debug=None):
        code, powid = self.get_code_and_powid()
        i = Invocation(self._server, self.db, code, powid)
        return i.invoke(args, args_clist, from_vatid, debug)

    def get_code_and_powid(self):
        c = self.db.cursor()
        c.execute("SELECT `code`,`powid` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        code, powid = res[0]
        return code, powid
