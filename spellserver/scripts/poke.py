
import os
import urllib
from . import webwait

def poke(so, out, err):
    message = so["message"]
    basedir = os.path.abspath(so["basedir"])
    dbfile = os.path.join(basedir, "control.db")
    if not (os.path.isdir(basedir) and os.path.exists(dbfile)):
        print >>err, "'%s' doesn't look like a spellserver basedir, quitting" % basedir
        return 1
    baseurl, vatid = webwait.wait(basedir, err)
    print "Node appears to be running, poking"
    r = urllib.urlopen(baseurl+"poke", message)
    print r.read()

