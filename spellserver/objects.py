
import os, json
from . import util

def create_object(db):
    objid = util.to_ascii(os.urandom(32), "obj0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?)",
              (objid, json.dumps({})))
    db.commit()
    return objid
