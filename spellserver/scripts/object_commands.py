
import os, json
from .. import memory, urbject, database, util

def get_db(so, err, basedir=None):
    if basedir is None:
        basedir = os.path.abspath(so["basedir"])
    dbfile = os.path.join(basedir, "control.db")
    if not (os.path.isdir(basedir) and os.path.exists(dbfile)):
        print >>err, "'%s' doesn't look like a spellserver basedir, quitting" % basedir
        return None
    sqlite, db = database.get_db(dbfile)
    return db

def create_memory_from_file(basedir, memory_file, err):
    db = get_db(None, err, basedir)
    if not db:
        return 1
    data = open(memory_file, "rb").read().decode("utf-8")
    memid = memory.create_raw_memory(db, json.dumps(data), "{}")
    return memid

def create_memory(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    if so["memory-file"]:
        data = open(so["memory-file"], "rb").read().decode("utf-8")
        json.loads(data) # make sure it's really JSON
    else:
        data = "{}"
    memid = memory.create_raw_memory(db, data, "{}")
    print >>out, "new memid: %s" % memid
    return 0

def list_memory(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    c = db.cursor()
    c.execute("SELECT `memid`,`data_json`, `data_clist_json` FROM `memory`")
    mems = c.fetchall()
    print >>out, "memid: size / clist-length"
    for (memid, data_json, clist_json) in sorted(mems):
        print >>out, "%s: %d / %s" % (memid, len(data_json),
                                      len(json.loads(clist_json)))
    print >>out, "%d memory slots total" % len(mems)
    return 0

def dump_memory(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    memid = so["memid"]
    c = db.cursor()
    c.execute("SELECT `data_json`, `data_clist_json` FROM `memory`"
              " WHERE `memid`=?", (memid,))
    mems = c.fetchall()
    if not mems:
        print >>out, "memid not found"
        return 0
    data_json, clist_json = mems[0]
    print >>out, "DATA:", data_json.strip()
    print >>out, "CLIST:", clist_json.strip()
    return 0

def create_urbject(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    c = db.cursor()
    c.execute("SELECT `pubkey` FROM `node`")
    (vatid,) = c.fetchone()
    powid = urbject.create_power_for_memid(db, so["memid"])
    code = open(so["code-file"], "rb").read().decode("utf-8")
    urbjid = urbject.create_urbject(db, powid, code)
    spid = util.make_spid(vatid, urbjid)
    print >>out, "new spid: %s" % spid
    return 0

def list_urbjects(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    c = db.cursor()
    c.execute("SELECT `pubkey` FROM `node`")
    (vatid,) = c.fetchone()
    c.execute("SELECT `urbjid`,`powid`, `code` FROM `urbjects`")
    objs = c.fetchall()
    print >>out, "urbjid: code-size"
    for (urbjid, powid, code) in sorted(objs):
        spid = util.make_spid(vatid, urbjid)
        print >>out, "%s: %d" % (spid, len(code))
    print >>out, "%d objects total" % len(objs)
    return 0

def dump_urbject(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    urbjid = so["urbjid"]
    if urbjid.startswith("spid0-"):
        vatid, urbjid = util.parse_spid(urbjid)
    print >>out, "vat:", vatid
    print >>out, "urbj:", urbjid
    c = db.cursor()
    c.execute("SELECT `powid`, `code` FROM `urbjects`"
              " WHERE `urbjid`=?", (urbjid,))
    mems = c.fetchall()
    if not mems:
        print >>out, "urbjid not found"
        return 0
    powid, code = mems[0]
    print >>out, "power:", powid
    c.execute("SELECT `power_json`, `power_clist_json` FROM `power`"
              " WHERE `powid`=?", (powid,))
    power_json, clist_json = c.fetchone()
    print >>out, "POWER:", power_json.strip()
    print >>out, "CLIST:", clist_json.strip()
    print >>out, "CODE:"
    print >>out, code.strip()
    return 0
