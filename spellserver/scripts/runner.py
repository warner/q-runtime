
# Only import stdlib at the top level. Do not import anything from our
# dependency set, or parts of spellserver that require things from the
# dependency set. It is only safe to import such things at runtime, inside a
# command that specifically needs it.

import os, sys, shutil

try:
    # do not import anything from Twisted that requires the reactor, to allow
    # 'ssp start' to choose a reactor itself
    from twisted.python import usage
except ImportError:
    print >>sys.stderr, "Unable to import Twisted."
    print >>sys.stderr, "Please run 'python setup.py build'"
    sys.exit(1)

DEFAULT_BASEDIR = os.path.expanduser("~/.spellserver")

class BasedirParameterMixin:
    optParameters = [
        ("basedir", "d", DEFAULT_BASEDIR, "Base directory"),
        ]
class BasedirArgument:
    def parseArgs(self, basedir=None):
        if basedir is not None:
            self["basedir"] = basedir

class StartArguments(BasedirArgument):
    def parseArgs(self, basedir=None, *twistd_args):
        # this can't handle e.g. 'ssp start --nodaemon', since then
        # --nodaemon looks like a basedir. Consider using (self, *all_args)
        # and searching for "--" to indicate the start of the twistd_args
        self.twistd_args = twistd_args
        BasedirArgument.parseArgs(self, basedir)

class CreateNodeOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    optParameters = [
        ("webport", "p", "tcp:0:interface=127.0.0.1",
         "TCP port for the node's HTTP interface."),
        ]

class StartNodeOptions(BasedirParameterMixin, StartArguments, usage.Options):
    optFlags = [
        ("no-open", "n", "Do not automatically open the control panel"),
        ]
class StopNodeOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    pass
class RestartNodeOptions(BasedirParameterMixin, StartArguments, usage.Options):
    def postOptions(self):
        self["no-open"] = False
class OpenOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    optFlags = [
        ("no-open", "n", "Don't open webbrowser, just show URL"),
        ]

class TestOptions(usage.Options):
    def parseArgs(self, *test_args):
        if not test_args:
            vmaj,vmin = sys.version_info[0:2]
            if vmaj == 2 and vmin < 7:
                print "Sorry, test-discovery requires py2.7"
                print "Try ./ssp test spellserver.test.test_netstrings"
                sys.exit(1)
            self.test_args = ["discover", "-v"] # require unittest from py2.7
        else:
            self.test_args = ["-v"] + list(test_args)

class Options(usage.Options):
    synopsis = "\nUsage: ssp <command>"
    subCommands = [("create-node", None, CreateNodeOptions, "Create a node"),
                   ("start", None, StartNodeOptions, "Start a node"),
                   ("stop", None, StopNodeOptions, "Stop a node"),
                   ("restart", None, RestartNodeOptions, "Restart a node"),
                   ("open", None, OpenOptions, "Open web control panel"),

                   ("test", None, TestOptions, "Run unit tests"),
                   ]

    def getUsage(self, **kwargs):
        t = usage.Options.getUsage(self, **kwargs)
        return t + "\nPlease run 'ssp <command> --help' for more details on each command.\n"

    def postOptions(self):
        if not hasattr(self, 'subOptions'):
            raise usage.UsageError("must specify a command")

def create_node(*args):
    from .create_node import create_node
    return create_node(*args)

def start(*args):
    from .startstop import start
    return start(*args)

def stop(*args):
    from .startstop import stop
    return stop(*args)

def restart(*args):
    from .startstop import restart
    return restart(*args)

def open_control_panel(*args):
    from .open import open_control_panel
    return open_control_panel(*args)


def test(so, stdout, stderr):
    import unittest
    if os.path.exists("_test"):
        shutil.rmtree("_test")
    args = ["python -m unittest"] + list(so.test_args)
    unittest.main(module=None, argv=args)
    #unittest.main(module="spellserver.test.test_netstrings", argv=args)
    sys.exit(0) # just in case

DISPATCH = {"create-node": create_node,
            "start": start,
            "stop": stop,
            "restart": restart,
            "open": open_control_panel,
            "test": test,
            }

def run(args, stdout, stderr):
    config = Options()
    try:
        config.parseOptions(args)
    except usage.error, e:
        c = config
        while hasattr(c, 'subOptions'):
            c = c.subOptions
        print >>stderr, str(c)
        print >>stderr, e.args[0]
        return 1
    command = config.subCommand
    so = config.subOptions
    try:
        rc = DISPATCH[command](so, stdout, stderr)
        return rc
    except ImportError, e:
        print >>stderr, "--- ImportError ---"
        print >>stderr, e
        print >>stderr, "Please run 'python setup.py build'"
        return 1
