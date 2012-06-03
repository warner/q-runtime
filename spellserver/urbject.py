
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
    def fill(self, inner_power, clist, memorized_dicts, used_memory):
        # inner_power is the dictionary passed to sandboxed code as power=
        self.inner_power = inner_power
        # .clist maps clids from .inner_power objects to real swissnums
        self.clist = clist
        # .memorized_dicts tracks Memory-backed dictionaries in .inner_power
        self.memorized_dicts = memorized_dicts
        # .used_memory tracks Memory objects that will need saving
        self.used_memory = used_memory

def unpack_power(db, power_json, clist_json):
    # create the inner power object, and the clist, and the memorylist
    outer_power = OuterPower()
    def inner_make_urbject(code, child_power):
        packed_power = pack_power(child_power, outer_power);
        powid = create_power(db, packed_power)
        urbjid = create_urbject(db, powid, code)
        return urbjid
    clist = json.loads(clist_json) # maps clids to swissnums
    memorized_dicts = {} # id(dict) -> Memory
    used_memory = {} # could be a Set if (Memory(a) is Memory(a)), but nope
    def hook(dct):
        if "__power__" in dct:
            ptype = dct["__power__"]
            clid = str(dct["clid"]) # points into the clist
            # str because 'clist' keys (like all JSON keys) are strings
            if ptype == "native":
                name = clist[clid]
                if name == "make_urbject":
                    return NativePower(inner_make_urbject, clid)
                raise ValueError("unknown native power %s" % (name,))
            if ptype == "memory":
                memid = clist[clid]
                m = Memory(db, memid)
                data = m.get_data()
                memorized_dicts[id(data)] = m
                used_memory[memid] = m
                return data
            if ptype == "reference":
                r = InnerReference(clid)
                return r
            raise ValueError("unknown power type %s" % (ptype,))
        return dct
    try:
        inner_power = json.loads(power_json, object_hook=hook)
    except:
        print "unpack_power exception, power_json='%s'" % power_json
        raise
    outer_power.fill(inner_power, clist, memorized_dicts, used_memory.values())
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
    def _iterencode_dict(self, dct, markers=None):
        if id(dct) in self._power_memorized_dicts:
            m = self._power_memorized_dicts[id(dct)]
            memid = m.memid
            new_clid = self._power_new_clist.add(memid)
            dct = {"__power__": "memory", "clid": new_clid}
        return json.JSONEncoder._iterencode_dict(self, dct, markers)

    def default(self, obj):
        if isinstance(obj, NativePower):
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

def pack_power(child_power, outer_power):
    enc = PowerEncoder()
    enc._power_old_clist = outer_power.clist
    enc._power_new_clist = power_clist = CList()
    enc._power_memorized_dicts = outer_power.memorized_dicts
    power_json = enc.encode(child_power)
    packed_power = PackedPower(power_json, json.dumps(power_clist))
    return packed_power

def execute(db, code, args, outer_power, from_vatid, debug=None):
    log.msg("EVAL <%s>" % (code,))
    log.msg("ARGS <%s>" % (args,))
    code = compile(code, "<from vatid %s>" % from_vatid, "exec")
    inner_power = outer_power.inner_power
    def log2(msg):
        log.msg(msg)
        print msg
    namespace = {"log": log2, "add": add}
    if debug:
        namespace["debug"] = debug
    eval(code, namespace, namespace)
    rc = namespace["call"](args, inner_power)
    del rc # rc is dropped for now
    for m in outer_power.used_memory:
        m.save()



class Urbject:
    def __init__(self, db, urbjid):
        self.db = db
        self.urbjid = urbjid

    def invoke(self, args, from_vatid, debug=None):
        code, powid = self.get_code_and_powid()
        outer_power = get_power(self.db, powid)
        return execute(self.db, code, args, outer_power, from_vatid, debug)

    def get_code_and_powid(self):
        c = self.db.cursor()
        c.execute("SELECT `code`,`powid` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        code, powid = res[0]
        return code, powid
