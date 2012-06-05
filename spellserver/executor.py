
import json
from twisted.application import service
from twisted.python import log
from . import urbject
from .memory import create_memory

class ExecutionServer(service.Service):
    def __init__(self, db, vatid, comms):
        self.db = db
        self.vatid = vatid
        self._comms_server = comms
        self._debug_processed_counter = 0

    def process_request(self, msg, from_vatid):
        # main request-execution handler
        log.msg("PROCESS %s" % (msg,))
        try:
            self._process_request(msg, from_vatid)
        except:
            # TODO: think through exception handling
            raise
        self._debug_processed_counter += 1

    def _process_request(self, msg, from_vatid):
        # really, you should ignore from_vatid
        command = str(msg["command"])
        if command == "execute":
            memid = str(msg["memid"])
            powid = urbject.create_power_for_memid(self.db, memid)
            t = urbject.Turn(self, self.db)
            t.start_turn(msg["code"], powid, msg["args_json"], "{}", from_vatid)
            return
        if command == "invoke":
            urbjid = str(msg["urbjid"])
            u = urbject.Urbject(self, self.db, urbjid)
            u.invoke(msg["args_json"], msg["args_clist_json"], from_vatid)
            return
        #raise ValueError("unknown command '%s'" % command)
        log.msg("ignored command '%s'" % command)

    def send_message(self, target_vatid, msg):
        self._comms_server.send_message(target_vatid, msg)

    # debug / CLI tools, triggered by 'poke'

    def send_execute(self, vatid, memid, code, args):
        msg = {"command": "execute",
               "memid": memid,
               "code": code,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps({})}
        self._comms_server.send_message(vatid, json.dumps(msg))

    def send_invoke(self, vatid, urbjid, args):
        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps({})}
        self._comms_server.send_message(vatid, json.dumps(msg))

    def poke(self, body):
        if body.startswith("send "):
            cmd, vatid = body.strip().split()
            cmd_s = json.dumps({"command": "hello"})
            self._comms_server.send_message(vatid, cmd_s)
            return "message sent"
        if body.startswith("create-memory"):
            memid = create_memory(self.db)
            return "created memory %s" % memid
        if body.startswith("execute "):
            cmd, vatid, memid = body.strip().split()
            code = ("def call(args, power):\n"
                    "    log('I have power!')\n")
            args = {"foo": 12}
            self.send_execute(vatid, memid, code, args)
            return "execute sent"
        if body.startswith("invoke "):
            cmd, vatid, urbjid = body.strip().split()
            args = {"foo": 12}
            self.send_invoke(vatid, urbjid, args)
            return "invoke sent"
        self._comms_server.trigger_inbound()
        self._comms_server.trigger_outbound()
        return "I am poked"
