
import os, json
from .. import memory, urbject, database

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
        data = {}
    memid = memory.create_raw_memory(db, data, "{}")
    print "new memid: %s" % memid
    return 0

def list_memory(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    c = db.cursor()
    c.execute("SELECT `memid`,`data_json`, `data_clist_json` FROM `memory`")
    mems = c.fetchall()
    print "memid: size / clist-length"
    for (memid, data_json, clist_json) in sorted(mems):
        print >>out, "%s: %d / %s" % (memid, len(data_json),
                                      len(json.loads(clist_json)))
    print "%d memory slots total" % len(mems)
    return 0

def create_urbject(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    powid = urbject.create_power_for_memid(db, so["memid"])
    code = open(so["code-file"], "rb").read().decode("utf-8")
    urbjid = urbject.create_urbject(db, powid, code)
    print "new urbject ID: %s" % urbjid
    return 0

def list_urbjects(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    c = db.cursor()
    c.execute("SELECT `urbjid`,`powid`, `code` FROM `urbjects`")
    objs = c.fetchall()
    print "urbjid: code-size / power-id"
    for (urbjid, powid, code) in sorted(objs):
        print >>out, "%s: %d / %s" % (urbjid, len(code), powid)
    print "%d objects total" % len(objs)
    return 0
