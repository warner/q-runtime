
import os, json
from . import util

def create_memory(db, contents={}, clist={}):
    # if clist={}, this is powerless
    memid = util.to_ascii(os.urandom(32), "mem0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?,?)",
              (memid, json.dumps(contents), json.dumps(clist)))
    db.commit()
    return memid

class Memory:
    def __init__(self, db, memid):
        self.db = db
        self.memid = memid

    def get_raw_data(self):
        c = self.db.cursor()
        c.execute("SELECT `data_json`,`data_clist_json` FROM `memory`"
                  " WHERE `memid`=?", (self.memid,))
        return c.fetchone()[0]

    def save(self, packed):
        c = self.db.cursor()
        c.execute("UPDATE `memory` SET `data_json`=?, `data_clist_json`=?"
                  " WHERE `memid`=?",
                  (packed.power_json, packed.power_clist_json,
                   self.memid))
        self.db.commit()
