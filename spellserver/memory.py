
import json
from . import util

def create_memory(db, contents={}, clist={}):
    # if clist={}, this is powerless
    return create_raw_memory(db, json.dumps(contents), json.dumps(clist))

def create_raw_memory(db, contents_json, clist_json):
    memid = util.makeid("mem0-")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?,?)",
              (memid, contents_json, clist_json))
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
        return c.fetchone()

    def save(self, packed):
        c = self.db.cursor()
        c.execute("UPDATE `memory` SET `data_json`=?, `data_clist_json`=?"
                  " WHERE `memid`=?",
                  (packed.power_json, packed.power_clist_json,
                   self.memid))
        self.db.commit()

    def get_static_data(self):
        c = self.db.cursor()
        c.execute("SELECT `data_json` FROM `memory`"
                  " WHERE `memid`=?", (self.memid,))
        return json.loads(c.fetchone()[0])

    def get_data(self):
        c = self.db.cursor()
        c.execute("SELECT `data_json`,`data_clist_json` FROM `memory`"
                  " WHERE `memid`=?", (self.memid,))
        data_json, data_clist_json = c.fetchone()
        return json.loads(data_json), json.loads(data_clist_json)
