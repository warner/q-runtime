
import os
from twisted.python import log
from . import util
from .memory import Memory

def create_urbject(db, memid, code):
    urbjid = util.to_ascii(os.urandom(32), "urb0-", encoding="base32")
    c = db.cursor()
    c.execute("SELECT COUNT() FROM `memory` WHERE `memid`=?", (memid,))
    if c.fetchone()[0] != 1:
        raise KeyError("no memid %s" % memid)
    c.execute("INSERT INTO `urbjects` VALUES (?,?,?)",
              (urbjid, code, memid))
    db.commit()
    return urbjid

class Power:
    pass

def execute(db, code, args, memid, from_vatid, debug=None):
    log.msg("EVAL <%s>" % (code,))
    log.msg("ARGS <%s>" % (args,))
    code = compile(code, "<from vatid %s>" % from_vatid, "exec")
    power = Power()
    memory = Memory(db, memid)
    power.memory = memory.get_data()
    namespace = {"log": log.msg}
    if debug:
        namespace["debug"] = debug
    eval(code, namespace, namespace)
    rc = namespace["call"](args, power)
    del rc # rc is dropped for now
    memory.save()


class Urbject:
    def __init__(self, db, urbjid):
        self.db = db
        self.urbjid = urbjid

    def invoke(self, args, from_vatid):
        memid, code = self.get_memid_and_code()
        return execute(self.db, code, args, memid, from_vatid)

    def get_memid_and_code(self):
        c = self.db.cursor()
        c.execute("SELECT `memid`,`code` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        memid, code = res[0]
        return memid, code
