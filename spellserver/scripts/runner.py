
# Only import stdlib at the top level. Do not import anything from our
# dependency set, or parts of spellserver that require things from the
# dependency set. It is only safe to import such things at runtime, inside a
# command that specifically needs it.

import os, sys

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

class GossipOptions(usage.Options):
    def parseArgs(self, *basedirs):
        self.basedirs = basedirs

class OpenOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    optFlags = [
        ("no-open", "n", "Don't open webbrowser, just show URL"),
        ]

class PokeOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    optParameters = [
        ("message", "m", "", "Message to send"),
        ]


class TestOptions(usage.Options):
    def parseArgs(self, *test_args):
        if not test_args:
            test_args = ["spellserver"]
        self.test_args = test_args

class SendOptions(BasedirParameterMixin, usage.Options):
    optFlags = [
        ("only", "o", "sendOnly: don't ask for return value"),
        ]
    def parseArgs(self, spid, args="{}"):
        self["spid"] = spid
        self["args"] = args
    def getSynopsis(self):
        return "Usage: ssp admin send SPID [ARGS-JSON]"

class CreateMemoryOptions(BasedirParameterMixin, BasedirArgument,
                          usage.Options):
    optParameters = [
        ("memory-file", "m", None, "file (JSON) with initial memory contents"),
        ]

    def getSynopsis(self):
        return "Usage: ssp admin create-memory BASEDIR"

class ListMemoryOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    def getSynopsis(self):
        return "Usage: ssp admin list-memory BASEDIR"

class DumpMemoryOptions(BasedirParameterMixin, BasedirArgument,
                          usage.Options):
    def parseArgs(self, basedir, memid):
        BasedirArgument.parseArgs(self, basedir)
        self["memid"] = memid

    def getSynopsis(self):
        return "Usage: ssp admin dump-memory BASEDIR MEMID"

class CreateUrbjectOptions(BasedirParameterMixin, BasedirArgument,
                           usage.Options):
    optFlags = [
        ("no-memory", None, "deny persistent storage"),
        ]
    optParameters = [
        ("memid", None, None, "memid to give to Urbject"),
        ("memory-file", "m", None, "file (JSON) with initial memory contents"),
        ]

    def parseArgs(self, basedir, codefile):
        BasedirArgument.parseArgs(self, basedir)
        if self["no-memory"]:
            self["memid"] = None
        elif self["memory-file"]:
            from .object_commands import create_memory_from_file
            # TODO: get stdout/stderr from options
            self["memid"] = create_memory_from_file(self["basedir"],
                                                    self["memory-file"],
                                                    sys.stderr)
        elif not self["memid"]:
            from .object_commands import create_memory_from_data
            # TODO: get stdout/stderr from options
            self["memid"] = create_memory_from_data(self["basedir"], {},
                                                    sys.stderr)
        self["code-file"] = codefile

    def getSynopsis(self):
        return "Usage: ssp admin create-urbject BASEDIR CODEFILE.py"

class ListUrbjectOptions(BasedirParameterMixin, BasedirArgument, usage.Options):
    def getSynopsis(self):
        return "Usage: ssp admin list-urbjects BASEDIR"

class DumpUrbjectOptions(BasedirParameterMixin, BasedirArgument,
                          usage.Options):
    def parseArgs(self, basedir, urbjid):
        BasedirArgument.parseArgs(self, basedir)
        self["urbjid"] = urbjid

    def getSynopsis(self):
        return "Usage: ssp admin dump-memory BASEDIR MEMID"

class AdminOptions(usage.Options):
    subCommands = [
        ("create-memory", None, CreateMemoryOptions, "Make a memory slot"),
        ("list-memory", None, ListMemoryOptions, "List all memory slots"),
        ("dump-memory", None, DumpMemoryOptions, "Display a memory slot"),
        ("create-urbject", None, CreateUrbjectOptions, "Make an Urbject"),
        ("list-urbjects", None, ListUrbjectOptions, "List all urbjects"),
        ("dump-urbject", None, DumpUrbjectOptions, "Display an Urbject"),
        ]
    def postOptions(self):
        if not hasattr(self, 'subOptions'):
            raise usage.UsageError("must specify a subcommand")

def create_memory(*args):
    from .object_commands import create_memory
    return create_memory(*args)

def list_memory(*args):
    from .object_commands import list_memory
    return list_memory(*args)

def dump_memory(*args):
    from .object_commands import dump_memory
    return dump_memory(*args)

def create_urbject(*args):
    from .object_commands import create_urbject
    return create_urbject(*args)

def list_urbjects(*args):
    from .object_commands import list_urbjects
    return list_urbjects(*args)

def dump_urbject(*args):
    from .object_commands import dump_urbject
    return dump_urbject(*args)

adminDispatch = {
    "create-memory": create_memory,
    "list-memory": list_memory,
    "dump-memory": dump_memory,
    "create-urbject": create_urbject,
    "list-urbjects": list_urbjects,
    "dump-urbject": dump_urbject,
    }

def do_admin(options, stdout, stderr):
    so = options.subOptions
    f = adminDispatch[options.subCommand]
    return f(so, stdout, stderr)

class Options(usage.Options):
    synopsis = "\nUsage: ssp <command>"
    subCommands = [
        ("create-node", None, CreateNodeOptions, "Create a node"),
        ("start", None, StartNodeOptions, "Start a node"),
        ("stop", None, StopNodeOptions, "Stop a node"),
        ("restart", None, RestartNodeOptions, "Restart a node"),
        ("open", None, OpenOptions, "Open web control panel"),
        ("gossip", None, GossipOptions, "Populate URL tables"),

        ("poke", None, PokeOptions, "Trigger event loop"),
        ("admin", None, AdminOptions, "admin commands"),

        ("send", None, SendOptions, "Send a message"),

        ("test", None, TestOptions, "Run unit tests with trial"),
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

def gossip(*args):
    from .gossip import gossip
    return gossip(*args)

def send(*args):
    from .send import send
    return send(*args)

def open_control_panel(*args):
    from .open import open_control_panel
    return open_control_panel(*args)

def poke(*args):
    from .poke import poke
    return poke(*args)

def test(so, stdout, stderr):
    from twisted.scripts import trial
    sys.argv = ["trial"] + list(so.test_args)
    trial.run()
    sys.exit(0) # just in case

DISPATCH = {"create-node": create_node,
            "start": start,
            "stop": stop,
            "restart": restart,
            "gossip": gossip,
            "send": send,
            "open": open_control_panel,
            "admin": do_admin,
            "poke": poke,
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
