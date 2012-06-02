
import os, json
from . import util

def create_memory(db):
    memid = util.to_ascii(os.urandom(32), "mem0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?)",
              (memid, json.dumps({})))
    db.commit()
    return memid


def get_data(db, memid):
    c = db.cursor()
    c.execute("SELECT `data_json` FROM `memory` WHERE `memid`=?", (memid,))
    data = c.fetchone()[0]
    return json.loads(data)

def set_data(db, memid, data):
    c = db.cursor()
    c.execute("UPDATE `memory` SET `data_json`=? WHERE `memid`=?",
              (json.dumps(data), memid,))
    db.commit()
