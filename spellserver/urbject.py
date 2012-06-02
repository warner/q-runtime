
import os, json
from twisted.python import log
from . import util
from .memory import Memory

def create_urbject(db, memid, code):
    urbjid = util.to_ascii(os.urandom(32), "urb0-", encoding="base32")
    c = db.cursor()
    c.execute("SELECT COUNT() FROM `memory` WHERE `memid`=?", (memid,))
    if c.fetchone()[0] != 1:
        raise KeyError("no memid %s" % memid)
    powid = util.to_ascii(os.urandom(32), "pow0-", encoding="base32")
    power_clist = {1: memid}
    power = {"memory": {"__power__": "memory", "clid": 1}}
    c.execute("INSERT INTO `power` VALUES (?,?,?)",
              (powid, json.dumps(power), json.dumps(power_clist)))
    c.execute("INSERT INTO `urbjects` VALUES (?,?,?)",
              (urbjid, code, powid))
    db.commit()
    return urbjid

def create_power(db, memid=None):
    powid = util.to_ascii(os.urandom(32), "pow0-", encoding="base32")
    power = {}
    power_clist = {}
    if memid:
        power["memory"] = {"__power__": "memory", "clid": 1}
        power_clist[1] = memid
    c = db.cursor()
    c.execute("INSERT INTO `power` VALUES (?,?,?)",
              (powid, json.dumps(power), json.dumps(power_clist)))
    db.commit()
    return powid

class Power:
    # this is passed into method invocation
    pass

class InnerReference:
    def __init__(self, clid):
        self.clid = clid
    def invoke(self, args):
        NotImplementedError

def unpack_power(db, power_json, clist_json):
    # create the inner power object, and the clist, and the memorylist
    clist = json.loads(clist_json) # maps clids to swissnums
    memlist = {}
    def hook(dct):
        if "__power__" in dct:
            ptype = dct["__power__"]
            clid = str(dct["clid"]) # points into the clist
            # str because 'clist' keys (like all JSON keys) are strings
            if ptype == "memory":
                m = Memory(db, clist[clid])
                memlist[clist[clid]] = m
                return m.get_data()
            if ptype == "reference":
                r = InnerReference(clid)
                return r
            raise ValueError("unknown power type %s" % (ptype,))
        return dct
    power = json.loads(power_json, object_hook=hook)
    return power, clist, memlist.values()


def get_power(db, powid):
    c = db.cursor()
    c.execute("SELECT `power_json`,`power_clist_json` FROM `power`"
              " WHERE `powid`=?", (powid,))
    (power_json, power_clist_json) = c.fetchone()
    power, clist, memlist = unpack_power(db, power_json, power_clist_json)
    return power, clist, memlist

def execute(db, code, args, inner_power, clist, memlist,
            from_vatid, debug=None):
    log.msg("EVAL <%s>" % (code,))
    log.msg("ARGS <%s>" % (args,))
    code = compile(code, "<from vatid %s>" % from_vatid, "exec")
    #def compartment_make_urbject(code, power):
    #    urbjid = create_urbject(db, memid, code)
    #    return urbjid
    #power.make_urbject = compartment_make_urbject

    namespace = {"log": log.msg}
    if debug:
        namespace["debug"] = debug
    eval(code, namespace, namespace)
    rc = namespace["call"](args, inner_power)
    del rc # rc is dropped for now
    for m in memlist:
        m.save()


class Urbject:
    def __init__(self, db, urbjid):
        self.db = db
        self.urbjid = urbjid

    def invoke(self, args, from_vatid):
        code, powid = self.get_code_and_powid()
        power, clist, memlist = get_power(self.db, powid)
        return execute(self.db, code, args, power, clist, memlist, from_vatid)

    def get_code_and_powid(self):
        c = self.db.cursor()
        c.execute("SELECT `code`,`powid` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        code, powid = res[0]
        return code, powid
