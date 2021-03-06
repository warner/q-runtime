
import json, copy, weakref
from twisted.python import log
from .memory import Memory, create_raw_memory
from .common import InnerReference, NativePower
from .pack import (pack_power, pack_memory, pack_args,
                   unpack_power, unpack_memory, unpack_args)
from .urbject import create_urbject, create_power, Urbject

# the inner (sandboxed) code gets a power= argument which contains static
# data, Memory-backed dicts (which behave just like static data but can be
# detected and serialized when creating a new object), and InnerReference
# objects (which have .send() and .call() methods).

# This is created from a power_json, in which power_json represents Memory
# objects with {__power__:"memory",swissnum:memid}, and InnerReference
# objects with {__power__:"reference",swissnum:[vatid,urbjid]}.

# To track these, the outer code (Turn) retains a bunch of tables that map
# from InnerReference to vatid/urbjid and back, and from the Memory-backed
# dicts to (memid, Memory) and back.

# when serializing (packing) a power= argument from the inner code, we do
# JSON serialization, but catch memory-backed dicts by comparing object
# identities with our table, and catch InnerReferences with isinstance().



class Turn:
    """This holds all the state for a single turn of the vat."""
    def __init__(self, server, db):
        self._server = server
        self._vatid = server.vatid
        self.db = db
        self.outbound_messages = []

        self._invocation_stack = []
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
            c.execute("SELECT `power_json` FROM `power` WHERE `powid`=?",
                      (powid,))
            results = c.fetchall()
            assert results, "no powid %s" % powid
            (power_json,) = results[0]
            inner = unpack_power(self, power_json)
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
            memory_json = memory.get_raw_data()
            data = unpack_memory(self, memory_json)
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
        # if make_urbject() is called with power.memory=M, inside an
        # Invocation that received M in its own power.memory, then the child
        # is supposed to share persistent access to M.
        if  (self._invocation_stack
             and self._invocation_stack[-1].memory_data_id
             and self._invocation_stack[-1].memory_data_id == id(data)):
            # this child will share the parent's Memory
            memid = self.memory_data_to_memid[id(data)]
        else:
            # otherwise, we want to create a new Memory object, with 'data'
            # as the initial contents
            packed = pack_memory(self, data)
            memid = create_raw_memory(self.db, packed)
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

    def start_turn(self, code, powid, args_json, from_vatid, debug=None):
        assert debug is None or callable(debug)
        first_invocation = Invocation(self, code, powid)
        self._invocation_stack.append(first_invocation)
        rc = first_invocation._invoke(args_json, from_vatid, debug)
        self._invocation_stack.pop()
        assert not self._invocation_stack
        self._commit_turn()
        return rc

    def local_sync_call(self, inner_ref, args):
        target_vatid, target_urbjid = self.swissnums[inner_ref]
        assert target_vatid == self._vatid # must be local
        ur = Urbject(self.db, target_urbjid)
        code, powid = ur.get_code_and_powid()
        next_invocation = Invocation(self, code, powid)
        self._invocation_stack.append(next_invocation)
        rc = next_invocation._execute(args, self._vatid)
        self._invocation_stack.pop()
        return rc

    def sendOnly(self, inner_ref, args):
        packed_args = pack_args(self, args)
        # local-only for now
        target_vatid, target_urbjid = self.swissnums[inner_ref]
        msg = {"command": "invoke",
               "urbjid": target_urbjid,
               "args_json": packed_args}
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
        self.memory_data_id = None
        if "memory" in self.inner_power:
            self.memory_data_id = id(self.inner_power["memory"])

    def _invoke(self, args_json, from_vatid, debug=None):
        assert debug is None or callable(debug)
        inner_args = unpack_args(self.turn, args_json)
        return self._execute(inner_args, from_vatid, debug)

    def _execute(self, args, from_vatid, debug=None):
        assert debug is None or callable(debug)
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

def inner_add(a, b):
    c = copy.copy(a) # shallow. We want p=add(power, stuff) to retain the
                     # object identity of "p.memory is power.memory"
    for key in b:
        c[key] = b[key]
    return c
