
import os
from .. import database

def gossip(so, out, err):
    # populate the 'vat_url' table in each node with all nodes
    basedirs = [os.path.abspath(basedir) for basedir in so.basedirs]
    vatids_and_urls = []

    for basedir in basedirs:
        dbfile = os.path.join(basedir, "control.db")
        if not (os.path.isdir(basedir) and os.path.exists(dbfile)):
            print >>err, "'%s' doesn't look like a qruntime basedir, quitting" % basedir
            return 1
        sqlite, db = database.get_db(dbfile, err)
        c = db.cursor()
        c.execute("SELECT webport,pubkey FROM node LIMIT 1")
        (webport,vatid) = c.fetchone()
        parts = webport.split(":")
        assert parts[0] == "tcp"
        portnum = int(parts[1])
        if portnum == 0:
            continue
        url = "http://localhost:%d/messages" % portnum
        vatids_and_urls.append( (vatid, url) )
    print "%d vats found" % len(vatids_and_urls)

    for basedir in basedirs:
        dbfile = os.path.join(basedir, "control.db")
        sqlite, db = database.get_db(dbfile, err)
        c = db.cursor()
        for vatid,url in vatids_and_urls:
            c.execute("INSERT INTO `vat_urls` VALUES (?,?)", (vatid, url))
        db.commit()
        print "%s updated" % basedir

    return 0
