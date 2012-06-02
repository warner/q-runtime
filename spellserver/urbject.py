
import os
from twisted.python import log
from . import util, memory

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

class Urbject:
    def __init__(self, db, urbjid):
        self.db = db
        self.urbjid = urbjid

    def invoke(self, args, from_vatid):
        memid, code = self.get_memid_and_code()
        return self.execute(code, args, memid, from_vatid)

    def get_memid_and_code(self):
        c = self.db.cursor()
        c.execute("SELECT `memid`,`code` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        memid, code = res[0]
        return memid, code

    def execute(self, code, args, memid, from_vatid):
        print "EVAL <%s>" % (code,)
        print "ARGS", args
        code = compile(code, "<from vatid %s>" % from_vatid, "exec")
        power = Power()
        power.memory = memory.get_data(self.db, memid)
        namespace = {"log": log.msg}
        eval(code, namespace, namespace)
        rc = namespace["call"](args, power)
        del rc # rc is dropped for now
        memory.set_data(self.db, memid, power.memory)
