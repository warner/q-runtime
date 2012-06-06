
import json
from . import util

def create_urbject(db, powid, code):
    urbjid = util.makeid("urb0-")
    c = db.cursor()
    c.execute("INSERT INTO `urbjects` VALUES (?,?,?)", (urbjid, powid, code))
    db.commit()
    return urbjid

def create_power(db, packed_power):
    powid = util.makeid("pow0-")
    c = db.cursor()
    c.execute("INSERT INTO `power` VALUES (?,?)", (powid, packed_power))
    db.commit()
    return powid

def create_power_for_memid(db, memid=None, grant_make_urbject=False):
    powid = util.makeid("pow0-")
    power = {}
    if memid:
        power["memory"] = {"__power__": "memory", "swissnum": memid}
    if grant_make_urbject:
        power["make_urbject"] = {"__power__": "native",
                                 "swissnum": "make_urbject"}
    c = db.cursor()
    c.execute("INSERT INTO `power` VALUES (?,?)",
              (powid, json.dumps(power)))
    db.commit()
    return powid



class Urbject:
    def __init__(self, server, db, urbjid):
        self._server = server
        self.db = db
        self.urbjid = urbjid

    def get_code_and_powid(self):
        c = self.db.cursor()
        c.execute("SELECT `code`,`powid` FROM `urbjects` WHERE `urbjid`=?",
                  (self.urbjid,))
        res = c.fetchall()
        if not res:
            raise KeyError("unknown urbjid %s" % self.urbjid)
        code, powid = res[0]
        return code, powid
