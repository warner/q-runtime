
import os
from .. import objects, database

def get_db(so, err):
    basedir = os.path.abspath(so["basedir"])
    dbfile = os.path.join(basedir, "control.db")
    if not (os.path.isdir(basedir) and os.path.exists(dbfile)):
        print >>err, "'%s' doesn't look like a spellserver basedir, quitting" % basedir
        return 1
    sqlite, db = database.get_db(dbfile)
    return db

def create_object(so, out, err):
    db = get_db(so, err)
    if db == 1:
        return db
    objid = objects.create_object(db)
    print "new objid: %s" % objid
    return 0

def list_objects(so, out, err):
    db = get_db(so, err)
    if db == 1:
        return db
    c = db.cursor()
    c.execute("SELECT `objid`,`data_json` FROM `memory`")
    objs = c.fetchall()
    print "objid: size"
    for (objid, data_json) in sorted(objs):
        print >>out, "%s: %d" % (objid, len(data_json))
    print "%d objects total" % len(objs)
    return 0

def create_method(so, out, err):
    db = get_db(so, err)
    if db == 1:
        return db
    objid = so.objid
    code = open(so.codefile, "r").read()
    methid = objects.create_method(db, objid, code)
    print "new methid: %s" % methid
    return 0
