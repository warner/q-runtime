
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
# detected and serialized when creating a new object), and InnerReference
# objects (which have .send() and .call() methods).

# This is created from a power_json/clist_json pair, in which power_json
# represents Memory objects with {__power__:"memory",clid=clid}, and
# InnerReference objects with {__power__:"reference",clid=clid}. clist_json
# maps clid to memid or (vatid,urbjid)

# To track these, the outer code (Turn) retains a bunch of tables that map
# from InnerReference to vatid/urbjid and back, and from the Memory-backed
# dicts to (memid, Memory) and back.

# when serializing (packing) a power= argument from the inner code, we do
# JSON serialization, but catch memory-backed dicts by comparing object
# identities with our table, and catch InnerReferences with isinstance().

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
        self.outbound_messages = []

        self.powid_to_power = {} # powid -> inner 'power' dict
        self.power_to_powid = {} # id(inner-dict) -> (powid, inner-dict)
        # retain inner-dict to keep it alive, so the id() isn't re-assigned

        self.KNOWN_NATIVE_POWERS = {"make_urbject": self.inner_make_urbject}
        self.native_powers = {} # name -> NativePower object

        # this makes sure that sub-invocations (via o.call) get the same data
        # as the parent, and that their modifications are immediately visible
        # to the parent
        self.memories = {} # memid -> (Memory, data)
        self.memory_data_to_memid = {} # id(data) -> memid

        self.references = {} # refid=(vatid,urbjid) -> InnerReference

        # this maps from an object (NativePower or InnerReference) to
        # swissnum, so when we see one during serialization (of args, power,
        # or a memory), we can look up the swissnum (which is otherwise
        # hidden from the inner code)
        self.swissnums = weakref.WeakKeyDictionary()

    def get_power(self, powid):
        if powid not in self.powid_to_power:
            c = self.db.cursor()
            c.execute("SELECT `power_json`,`power_clist_json` FROM `power`"
                      " WHERE `powid`=?", (powid,))
            results = c.fetchall()
            assert results, "no powid %s" % powid
            (power_json, power_clist_json) = results[0]
            inner = unpack_power(self, power_json, power_clist_json)
            self.powid_to_power[powid] = inner
            self.power_to_powid[id(inner)] = (powid, inner)
        return self.powid_to_power[powid]

    def inner_make_urbject(self, code, child_power):
        """Implement a make_urbject() function for the inner code."""
        # When called later, the packer will need to pull swissnums from the
        # Turn, and compare both .power and .memory to see if we're sharing
        # power or memory with the child. So we need to stash them
        if id(child_power) in self.power_to_powid:
            # reuse the existing powid instead of creating a new one
            (powid,_) = self.power_to_powid[id(child_power)]
        else:
            packed_power = pack_power(self, child_power)
            powid = create_power(self.db, packed_power)
        urbjid = create_urbject(self.db, powid, code)
        # this will update Invocation.swissnums, so it will have the
        # ability to serialize the newly created object at the end of the
        # turn
        ir = InnerReference(self)
        assert self._vatid
        self.swissnums[ir] = (self._vatid, urbjid)
        return ir

    def get_native_power(self, name):
        if name not in self.native_powers:
            if name not in self.KNOWN_NATIVE_POWERS:
                raise ValueError("unknown native power %s" % (name,))
            f = self.KNOWN_NATIVE_POWERS[name]
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
            self.memory_data_to_memid[id(data)] = memid
            self.memories[memid] = (memory, data)
        (memory, data) = self.memories[memid]
        return data

    def get_reference(self, refid):
        # JSON returns lists, but we need refid to be hashable
        assert isinstance(refid, tuple)
        if refid not in self.references:
            r = InnerReference(self)
            self.references[refid] = r
            self.swissnums[r] = refid
        return self.references[refid]

    # serialization/packing
    def put_memory(self, data):
        if id(data) in self.memory_data_to_memid:
            # we've seen this before, so this child will share the parent's
            # Memory
            memid = self.memory_data_to_memid[id(data)]
        else:
            # otherwise, we want to create a new Memory object, with 'data'
            # as the initial contents
            packed = pack_memory(self, data)
            memid = create_raw_memory(self.db, packed.power_json,
                                      packed.power_clist_json)
            # note: we do *not* do "self.swissnums[data] = memid" here. We
            # only re-use Memory objects that were passed into an inner
            # function via its power.memory . Passing the same initial data
            # to two separate make_urbject() calls does not give them shared
            # memory. OTOH, we may want to revisit this, if there's a good
            # way to express it (probably with an explicit make_memory()
            # call).
        return memid

    def get_swissnum_for_object(self, obj):
        return self.swissnums[obj]

    # this is the real entry point. Inside start_turn(), we'll use the
    # deserialization stuff above. The inner code may end up invoking
    # local_sync_call (when it does o.call), or outbound_message (for
    # o.send). When we're all done, we commit the turn.

    def start_turn(self, code, powid, args_json, args_clist_json, from_vatid,
                   debug=None):
        first_i = Invocation(self, code, powid)
        rc = first_i._invoke(args_json, args_clist_json, from_vatid, debug)
        self._commit_turn()
        return rc

    def local_sync_call(self, inner_ref, args):
        target_vatid, target_urbjid = self.swissnums[inner_ref]
        assert target_vatid == self._vatid # must be local
        ur = Urbject(self._server, self.db, target_urbjid)
        code, powid = ur.get_code_and_powid()
        rc = Invocation(self, code, powid)._execute(args, self._vatid)
        return rc

    def outbound_message(self, inner_ref, args):
        packed_args = pack_args(self, args)
        # local-only for now
        target_vatid, target_urbjid = self.swissnums[inner_ref]
        msg = {"command": "invoke",
               "urbjid": target_urbjid,
               "args_json": packed_args.power_json,
               "args_clist_json": packed_args.power_clist_json}
        # queue for delivery at the end of the turn
        self.outbound_messages.append( (target_vatid, json.dumps(msg)) )
        return None # no results-Promises yet

    def _commit_turn(self):
        for (memid, (memory, data)) in self.memories.items():
            memory.save(pack_memory(self, data))
        for (target_vatid, msg) in self.outbound_messages:
            self._server.send_message(target_vatid, msg)

class Invocation:
    def __init__(self, turn, code, powid):
        self.code = code
        self.turn = turn

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

class _PowerEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, NativePower) and self._power_packing._allow_native:
            p = self._power_packing
            name = p._turn.get_swissnum_for_object(obj)
            new_clid = p._clist.add(name)
            return {p._nonce: "native", "clid": new_clid}
        if isinstance(obj, InnerReference):
            p = self._power_packing
            refid = p._turn.get_swissnum_for_object(obj)
            new_clid = p._clist.add(refid)
            return {p._nonce: "reference", "clid": new_clid}
        return json.JSONEncoder.default(self, obj)
    def _iterencode_dict(self, dct, markers=None):
        # prevent dicts with keys named "__power__". The nonce-based defense
        # we have here is driven by Javascript's JSON.stringify which makes
        # it easy to prohibit specific key names. In python, we could do this
        # by overriding _iterencode_dict. There's not a lot of point, though,
        # since python code is unconfined anyways (they could just
        # monkeypatch us to remove this check, etc).
        if "__power__" in dct:
            raise ValueError("forbidden __power__ in serializing data")
        return json.JSONEncoder._iterencode_dict(self, dct, markers)

class _Packing:
    def __init__(self, turn, allow_native, allow_memory):
        self._turn = turn
        self._allow_native = allow_native
        self._allow_memory = allow_memory
        self._clist = CList()
        # we translate _nonce into "__power__" when we're done, and otherwise
        # prohibit "__power__" as a property name. This prevents inner code
        # from turning swissnums into references by submitting tricky data
        # for serialization.
        self._nonce = "__power_%s__" % os.urandom(32).encode("hex")
        self._enc = _PowerEncoder()
        self._enc._power_packing = self

    def _build_fake_memory(self, old_memory):
        memid = self._turn.put_memory(old_memory)
        new_clid = self._clist.add(memid)
        return {self._nonce: "memory", "clid": new_clid}

    def _pack(self, child_power):
        if self._allow_memory:
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

        new_power_json = self._enc.encode(child_power)
        new_power_json = new_power_json.replace(self._nonce, "__power__")
        packed = PackedPower(new_power_json, json.dumps(self._clist))
        return packed

def pack_power(turn, child_power):
    # updates turn.swissnums, turn.native_powers, and turn.memories . Returns
    # inner_power.
    p = _Packing(turn, allow_native=True, allow_memory=True)
    return p._pack(child_power)

def pack_memory(turn, child_power):
    # updates turn.swissnums . Returns data. You need to update turn.memories
    p = _Packing(turn, allow_native=False, allow_memory=False)
    return p._pack(child_power)

def pack_args(turn, child_power):
    # updates turn.swissnums . Returns inner_power.
    p = _Packing(turn, allow_native=False, allow_memory=False)
    return p._pack(child_power)

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
                refid = tuple(old_clist[old_clid])
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
    return up.unpack(power_json, clist_json)

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
        t = Turn(self._server, self.db)
        code, powid = self.get_code_and_powid()
        rc = t.start_turn(code, powid, args, args_clist, from_vatid, debug)
        return rc

    def get_code_and_powid(self):
        c = self.db.cursor()
        c.execute("SELECT `code`,`powid` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        code, powid = res[0]
        return code, powid
