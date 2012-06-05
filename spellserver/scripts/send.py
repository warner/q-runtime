
import os, json, urllib
from . import webwait

def send(so, out, err):
    json.loads(so["args"]) # make sure it's really JSON
    basedir = os.path.abspath(so["basedir"])
    dbfile = os.path.join(basedir, "control.db")
    if not (os.path.isdir(basedir) and os.path.exists(dbfile)):
        print >>err, "'%s' doesn't look like a spellserver basedir, quitting" % basedir
        return 1
    baseurl, vatid = webwait.wait(basedir, err)
    message = "send "+json.dumps({"spid": so["spid"],
                                  "args": so["args"],
                                  })
    r = urllib.urlopen(baseurl+"poke", message)
    print >>out, r.read()
    return 0

