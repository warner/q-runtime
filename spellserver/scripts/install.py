
import os, json
from .. import memory, urbject, util
from .object_commands import get_db

def install(so, out, err):
    db = get_db(so, err)
    if not db:
        return 1
    c = db.cursor()
    c.execute("SELECT `pubkey` FROM `node`")
    (vatid,) = c.fetchone()
    codedir = so["codedir"]
    memory_file = os.path.join(codedir, "memory.json")
    memid = None
    if os.path.exists(memory_file):
        data = open(memory_file, "rb").read().decode("utf-8")
        memid = memory.create_raw_memory(db, data, "{}")
    powid = urbject.create_power_for_memid(db, memid, True)
    for fn in os.listdir(codedir):
        if not fn.endswith(".py"):
            continue
        funcname = os.path.splitext(fn)[0]
        code = open(os.path.join(codedir, fn), "rb").read().decode("utf-8")
        urbjid = urbject.create_urbject(db, powid, code)
        spid = util.make_spid(vatid, urbjid)
        print >>out, "%s: %s" % (funcname, spid)
