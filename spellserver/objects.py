
import os, json
from . import util

def create_object(db):
    objid = util.to_ascii(os.urandom(32), "obj0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?)",
              (objid, json.dumps({})))
    db.commit()
    return objid

def create_method(db, objid, code):
    methid = util.to_ascii(os.urandom(32), "meth0-", encoding="base32")
    c = db.cursor()
    c.execute("SELECT COUNT() FROM `memory` WHERE `objid`=?", (objid,))
    if c.fetchone()[0] != 1:
        raise KeyError("no objid %s" % objid)
    c.execute("INSERT INTO `methods` VALUES (?,?,?)",
              (methid, objid, code))
    db.commit()
    return methid
