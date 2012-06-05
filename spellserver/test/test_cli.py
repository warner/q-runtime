
from StringIO import StringIO
from twisted.trial import unittest
from .common import ServerBase
from ..scripts import runner

CODE = """
def call(args, power):
    power['memory'] = 1234
"""

class CLI(ServerBase, unittest.TestCase):
    def runcli(self, *argv):
        stdout = StringIO(); stderr = StringIO()
        rc = runner.run(argv, stdout, stderr)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_cli(self):
        b = self.basedir
        def run(*argv):
            rc,out,err = self.runcli("admin", *argv)
            self.failUnlessEqual(rc, 0, "rc=%d out=%s err=%s" % (rc,out,err))
            return out
        out = run("create-memory", b)
        self.failUnless(out.startswith("new memid: "), out)
        memid = out.split()[2]
        self.failUnless(memid.startswith("mem0-"), memid)
        out = run("list-memory", b)
        lines = out.splitlines()
        self.failUnlessEqual(lines[0], "memid: size / clist-length")
        self.failUnlessEqual(lines[1], "%s: 2 / 0" % memid)
        self.failUnlessEqual(lines[-1], "1 memory slots total")
        out = run("dump-memory", b, memid)
        self.failUnless("DATA: {}" in out, out)
        self.failUnless("CLIST: {}" in out, out)

        codefile = self.mktemp()
        f = open(codefile, "wb")
        f.write(CODE)
        f.close()
        out = run("create-urbject", b, codefile)
        self.failUnless(out.startswith("new urbject ID: "), out)
        urbjid = out.split()[3]
        self.failUnless(urbjid.startswith("urb0-"), urbjid)
        lines = run("list-urbjects", b).splitlines()
        self.failUnlessEqual(lines[0], "urbjid: code-size / power-id")
        self.failUnless(lines[1].startswith("%s: 51 / " % urbjid), lines[1])
        self.failUnlessEqual(lines[-1], "1 objects total")

