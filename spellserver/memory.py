
import os, json
from . import util

def create_memory(db, contents={}):
    memid = util.to_ascii(os.urandom(32), "mem0-", encoding="base32")
    c = db.cursor()
    c.execute("INSERT INTO `memory` VALUES (?,?,?)",
              (memid, json.dumps(contents), json.dumps({})))
    db.commit()
    return memid

class Memory:
    def __init__(self, db, memid):
        self.db = db
        self.memid = memid

    def get_raw_data(self):
        # return a data object, which can be modified in place. Call .save()
        # afterwards!
        c = self.db.cursor()
        c.execute("SELECT `data_json` FROM `memory` WHERE `memid`=?",
                  (self.memid,))
        data_json = c.fetchone()[0]
        self.data = json.loads(data_json)
        return self.data

    def get_data(self, unpacker):
        # return an inner data object, which can be modified in place. Call
        # .save() afterwards!
        c = self.db.cursor()
        c.execute("SELECT `data_json`,`data_clist_json` FROM `memory`"
                  " WHERE `memid`=?", (self.memid,))
        data_json, data_clist_json = c.fetchone()[0]
        self.data = unpacker(data_json, data_clist_json)
        return self.data

    def save(self, packer=None):
        if not packer:
            def packer(data):
                from .urbject import PackedPower
                pp = PackedPower(json.dumps(data), json.dumps({}))
                return pp
        packed_power = packer(self.data)
        c = self.db.cursor()
        c.execute("UPDATE `memory` SET `data_json`=?, `data_clist_json`=?"
                  " WHERE `memid`=?",
                  (packed_power.power_json, packed_power.power_clist_json,
                   self.memid))
        self.db.commit()
