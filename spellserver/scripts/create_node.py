import os, sys

import nacl
from .. import util, database

def create_node(so, stdout=sys.stdout, stderr=sys.stderr):
    basedir = so["basedir"]
    if os.path.exists(basedir):
        print >>stderr, "basedir '%s' already exists, refusing to touch it" % basedir
        return 1
    os.mkdir(basedir)
    sqlite, db = database.get_db(os.path.join(basedir, "control.db"), stderr)
    c = db.cursor()
    pk, sk = nacl.crypto_box_keypair()
    pk_s = util.to_ascii(pk, "pk0-", encoding="base32")
    sk_s = util.to_ascii(sk, "sk0-", encoding="base32")
    c.execute("INSERT INTO node (webport, pubkey, privkey) VALUES (?,?,?)",
              (so["webport"], pk_s, sk_s))
    db.commit()
    print >>stdout, "node created in %s" % basedir
    return 0


