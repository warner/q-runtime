
import os, json
from . import util

def create_memory(db):
    memid = util.to_ascii(os.urandom(32), "mem0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?)",
              (memid, json.dumps({})))
    db.commit()
    return memid

class Memory:
    def __init__(self, db, memid):
        self.db = db
        self.memid = memid

    def get_data(self):
        # return a data object, which can be modified in place. Call .save()
        # afterwards!
        c = self.db.cursor()
        c.execute("SELECT `data_json` FROM `memory` WHERE `memid`=?",
                  (self.memid,))
        data_json = c.fetchone()[0]
        self.data = json.loads(data_json)
        return self.data

    def save(self):
        c = self.db.cursor()
        c.execute("UPDATE `memory` SET `data_json`=? WHERE `memid`=?",
                  (json.dumps(self.data), self.memid,))
        self.db.commit()
