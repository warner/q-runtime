
import os, json
from . import util

def create_memory(db):
    memid = util.to_ascii(os.urandom(32), "mem0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?)",
              (memid, json.dumps({})))
    db.commit()
    return memid
