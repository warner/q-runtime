
import re
from StringIO import StringIO
from twisted.trial import unittest
from twisted.internet.threads import deferToThread
from .common import ServerBase
from .pollmixin import PollMixin
from ..scripts import runner
from ..util import parse_spid
from ..memory import Memory

CODE = """
def call(args, power):
    power['memory']['data'] = 1234
    log('test_cli called')
"""

class CLI(ServerBase, PollMixin, unittest.TestCase):
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
        self.failUnless(out.startswith("new spid: "), out)
        spid = out.split()[2]
        vatid, urbjid = parse_spid(spid)
        lines = run("list-urbjects", b).splitlines()
        self.failUnlessEqual(lines[0], "urbjid: code-size")
        self.failUnlessEqual(lines[1], "%s: 86" % spid)
        self.failUnlessEqual(lines[-1], "1 objects total")

        lines = run("dump-urbject", b, spid).splitlines()
        self.failUnlessEqual(lines[0], "vat: %s" % vatid)
        self.failUnlessEqual(lines[1], "urbj: %s" % urbjid)
        memid = re.search(r'(mem0-\w+)', lines[4]).group(1)
        m = Memory(self.db, memid)
        self.failUnlessEqual(m.get_static_data(), {})

        #rc,out,err = self.runcli("send", "-d", b, spid)
        # 'send' does a blocking urlopen() call, so we have to call it from a
        # thread
        d = deferToThread(self.runcli, "send", "-d", b, spid)
        def _sent(res):
            rc,out,err = res
            self.failUnlessEqual(rc, 0, "rc=%d out=%s err=%s" % (rc,out,err))
            self.failUnlessEqual(out.strip(), "message sent")
            # now wait for it to be executed
            return self.poll(lambda: self.executor._debug_processed_counter >= 1)
        d.addCallback(_sent)
        def _then(ign):
            m = Memory(self.db, memid)
            self.failUnlessEqual(m.get_static_data(), {"data": 1234})
        d.addCallback(_then)
        return d
