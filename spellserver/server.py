import base64, time, json
from binascii import hexlify, unhexlify

from twisted.application import service
from twisted.web.client import getPage
from twisted.python import log
from foolscap.api import eventually
from nacl import crypto_box, crypto_box_open, \
     crypto_box_NONCEBYTES, crypto_box_PUBLICKEYBYTES
from . import util, urbject
from .memory import create_memory



# resending messages: we use Waterken's "retry-forever" style. Ideally, we'd
# like messages to any given Vat to be resent on an exponential backoff
# timer: the first time we try to send a message and get a rejected
# connection, we should wait 5 seconds before trying again, then 10 seconds,
# then 20, etc, capping the backoff at an hour or two. In addition, each time
# a new message is added to the queue for that Vat, we should make an
# immediate attempt (but not affect the timer). Any success resets the timer.
# The pending (unACKed) messages live in the database. So what this will
# really want is something that looks at the DB, computes a next-retry-time
# for each VatID that has pending messages, takes the minimum of those times,
# then sets a timer to wake up at that point. Maybe the whole retry schedule
# should be put in the DB, so if this server sleeps through the attempts, it
# wakes up doing the slow-poll instead of the fast-poll.

# also, consider the differences between TCP connection failures and
# delayed/lost ACKs. We actually care about the ACK. But we need to give them
# a reasonable amount of time to receive and store the message, especially
# for large messages. (scheduling a retry 5 seconds after we start sending a
# multi-minute message would be a disaster). So, do an HTTP send, if it
# succeeds (i.e. the encrypted response contains an ACK), then the message is
# retired. If and when it fails, start the timer. (this allows Vats to stall
# forever, but that's their perogative, and resending early to such a vat
# won't do any good).

class Server(service.MultiService):
    def __init__(self, db, pubkey_s, privkey_s):
        service.MultiService.__init__(self)
        self.db = db

        self.vatid = pubkey_s
        self.pubkey = util.from_ascii(pubkey_s, "pk0-", encoding="base32")
        self.privkey_s = privkey_s
        self.privkey = util.from_ascii(privkey_s, "sk0-", encoding="base32")

        self.inbound_triggered = False
        self.outbound_triggered = False

        self._debug_processed_counter = 0

    # nonce management: we need four virtual channels: one pair in each
    # direction. The Request channels deliver boxed request messages
    # (len+pubkey+nonce+encbody, where body is target+JSONargs or something).
    # The Response channels deliver boxed empty (ACK) messages
    # (len+pubkey+nonce+encbody where body=""). Each server remembers and
    # retransmits its (encrypted) outbound request with nonce N until it sees
    # an ACK with a corresponding nonce N. The directions are determined by
    # comparing base32ified pubkeys: 'First' has the lexicographically lower
    # pubkey, 'Second' has the higher pubkey. The actual nonces are:
    #  First->Second: request = 4*N+0, response = 4*N+1
    #  Second->First: request = 4*N+2, response = 4*N+3
    # The Request messages are sent in the body of an HTTP request. The
    # Response messages are returned in the HTTP response.

    def inbound_message(self, body):
        their_vatid, their_pubkey, nonce, encbody = self.parse_message(body)
        # their_vatid is "pk0-base32..", while their_pubkey is binary
        nonce_number = int(hexlify(nonce), 16)
        if their_vatid < self.vatid:
            offset = 2 # they are First, I am Second, msg is First->Second
        else:
            offset = 0 # I am First, they are Second, msg is Second->First
        assert nonce_number % 4 == offset, "wrong nonce type %d %d" % (nonce_number, offset)
        msg = crypto_box_open(encbody, nonce, their_pubkey, self.privkey)
        resp = self.process_message(their_vatid, nonce_number, offset, msg)
        r_nonce = self.number_to_nonce(nonce_number+1)
        return ",".join(["v0",
                         util.to_ascii(self.pubkey, "pk0-", encoding="base32"),
                         util.to_ascii(r_nonce, encoding="base32"),
                         crypto_box(resp, r_nonce, their_pubkey, self.privkey)])

    def number_to_nonce(self, number):
        nonce = unhexlify("%048x" % number)
        assert len(nonce) == crypto_box_NONCEBYTES
        return nonce

    def process_message(self, their_vatid, nonce_number, offset, msg):
        # the message is genuine, but might be a replay, or from the future
        c = self.db.cursor()
        c.execute("SELECT next_msgnum FROM inbound_msgnums"
                  " WHERE from_vatid=? LIMIT 1", (their_vatid,))
        data = c.fetchall()
        if data:
            next_msgnum = data[0][0]
        else:
            c.execute("INSERT INTO inbound_msgnums VALUES (?,?)",
                      (their_vatid, 0))
            self.db.commit()
            next_msgnum = 0
        expected_nonce = 4*next_msgnum+offset
        # If the nonce is old, we remember processing this message, so just
        # ACK it. If the nonce is too new, signal an error: that either means
        # we've been rolled back, or they're sending nonces from the future.
        # If the nonce is just right, process the message.
        if nonce_number > expected_nonce:
            log.msg("future: got %d, expected %d" % (nonce_number, expected_nonce))
            raise ValueError("begone ye futuristic demon message!")
        if nonce_number < expected_nonce:
            log.msg("old: got %d, current is %d" % (nonce_number, expected_nonce))
            return "ack (old)"
        log.msg("current: %d" % nonce_number)
        # add the message to the inbound queue. Once safe, ack.
        msg_json = msg.decode("utf-8")
        c.execute("INSERT INTO `inbound_messages` VALUES (?,?,?)",
                  (their_vatid, next_msgnum, msg_json))
        c.execute("UPDATE `inbound_msgnums`"
                  " SET `next_msgnum`=?"
                  " WHERE `from_vatid`=?",
                  (next_msgnum+1, their_vatid))
        self.db.commit()
        self.trigger_inbound()
        return "ack (new)"

    def trigger_inbound(self):
        if not self.inbound_triggered:
            self.inbound_triggered = True
            eventually(self.deliver_inbound_messages)

    def deliver_inbound_messages(self):
        self.inbound_triggered = False
        # we are now responsible for processing all queued messages, or
        # calling trigger_inbound() to reschedule ourselves for later

        c = self.db.cursor()
        c.execute("SELECT `from_vatid` FROM `inbound_messages`")
        vatids = sorted([res[0] for res in c.fetchall()])
        if not vatids:
            return
        vatid = vatids[0] # service First-er vat first, no particular reason
        c.execute("SELECT `msgnum` FROM `inbound_messages`"
                  " WHERE `from_vatid` = ?", (vatid,))
        msgnum = sorted([res[0] for res in c.fetchall()])[0]
        c.execute("SELECT `message_json` FROM `inbound_messages`"
                  " WHERE `from_vatid`=? AND `msgnum`=?",
                  (vatid, msgnum))
        (msg_json,) = c.fetchone()
        msg = json.loads(msg_json)

        # TODO: catch errors in process_request(), specifically inside the
        # eval() and call() that it performs. Those failures (which are
        # repeatable) still allow us to retire the message. It's only system
        # failures (loss of power, node shutdown) that allow messages to be
        # tried again.
        self.process_request(msg, vatid)
        self._debug_processed_counter += 1

        # if that completes, we can retire the message
        c.execute("DELETE FROM `inbound_messages`"
                  " WHERE `from_vatid`=? and `msgnum`=?",
                  (vatid, msgnum))
        self.db.commit()

        # now, do we have more work to do?
        c.execute("SELECT `from_vatid` FROM `inbound_messages`")
        vatids = [res[0] for res in c.fetchall()]
        if vatids:
            self.trigger_inbound() # more work to do, later

    def send_message(self, their_vatid, msg):
        assert isinstance(msg, (str, unicode)), "should be a json object, not %s" % type(msg)
        assert msg.startswith("{")
        c = self.db.cursor()
        c.execute("SELECT `next_msgnum` FROM `outbound_msgnums`"
                  " WHERE `to_vatid`=? LIMIT 1", (their_vatid,))
        data = c.fetchall()
        if data:
            next_msgnum = data[0][0]
        else:
            c.execute("INSERT INTO outbound_msgnums VALUES (?,?)",
                      (their_vatid, 0))
            self.db.commit()
            next_msgnum = 0
        # add the boxed message to the outbound queue
        if their_vatid < self.vatid:
            offset = 0 # they are First, I am Second, msg is Second->First
        else:
            offset = 2 # I am First, they are Second, msg is First->Second
        nonce = self.number_to_nonce(4*next_msgnum+offset)
        their_pubkey = util.from_ascii(their_vatid, "pk0-", encoding="base32")
        boxed = ",".join(["v0",
                          util.to_ascii(self.pubkey, "pk0-", encoding="base32"),
                          util.to_ascii(nonce, encoding="base32"),
                          crypto_box(msg, nonce, their_pubkey, self.privkey)])
        c.execute("INSERT INTO `outbound_messages` VALUES (?,?,?,?)",
                  (their_vatid, 0, next_msgnum, base64.b64encode(boxed)))
        c.execute("UPDATE `outbound_msgnums`"
                  " SET `next_msgnum`=?"
                  " WHERE `to_vatid`=?",
                  (next_msgnum+1, their_vatid))
        self.db.commit()
        self.trigger_outbound()

    def trigger_outbound(self):
        if not self.outbound_triggered:
            self.outbound_triggered = True
            eventually(self.deliver_outbound_messages)

    def deliver_outbound_messages(self):
        self.outbound_triggered = False
        # we are now responsible for transmitting all queued messages. Hm,
        # not sure this is a good way.
        c = self.db.cursor()
        now = time.time()
        not_recent = now - 60; # for now, retry every minute
        c.execute("SELECT `to_vatid` FROM `outbound_messages`"
                  " WHERE `last_sent` < ?", (not_recent,))
        vatids = [res[0] for res in c.fetchall()]
        for vatid in vatids:
            self.deliver_outbound_messages_to_vatid(vatid)

    def deliver_outbound_messages_to_vatid(self, vatid):
        c = self.db.cursor()
        c.execute("SELECT `msgnum` FROM `outbound_messages`"
                  " WHERE `to_vatid` = ?", (vatid,))
        msgnums = [res[0] for res in c.fetchall()]
        c.execute("SELECT `url` FROM `vat_urls`"
                  " WHERE `vatid` = ?", (vatid,))
        urls = [str(res[0]) for res in c.fetchall()]
        if not urls:
            log.msg("warning: sending msg to vatid %s but have no URL" % vatid)
        for msgnum in sorted(msgnums):
            c.execute("SELECT `message_b64` FROM `outbound_messages`"
                      " WHERE `to_vatid`=? AND `msgnum`=?",
                      (vatid, msgnum))
            (msg_b64,) = c.fetchone()
            msg = base64.b64decode(msg_b64)
            for url in urls:
                d = getPage(url, method="POST", postdata=msg,
                            followRedirect=True, timeout=60)
                d.addCallback(self._outbound_response, vatid, msgnum)
                d.addErrback(self._outbound_error)

    def _outbound_response(self, response, their_vatid, msgnum):
        if their_vatid < self.vatid:
            offset = 0 # they are First, I am Second, msg is Second->First
        else:
            offset = 2 # I am First, they are Second, msg is First->Second
        expected_nonce = self.number_to_nonce(4*msgnum+offset+1)
        pubkey_s, pubkey, nonce, encbody = self.parse_message(response)
        assert pubkey_s == their_vatid, (pubkey_s, their_vatid)
        assert nonce == expected_nonce, (int(hexlify(nonce),16), 4*msgnum+offset+1)
        msg = crypto_box_open(encbody, nonce, pubkey, self.privkey)
        log.msg("response msg: %s" % msg)
        # we don't actually look at the contents, just getting a valid boxed
        # response back is proof of success. We can now retire it.
        c = self.db.cursor()
        c.execute("DELETE FROM `outbound_messages`"
                  " WHERE `to_vatid`=? AND `msgnum`=?",
                  (their_vatid, msgnum))
        self.db.commit()

    def _outbound_error(self, f):
        print f

    def parse_message(self, body):
        # msg is "v0,pk0-pubkey_b32,nonce_b32,encbody", encbody is binary
        v0_s, pubkey_s, nonce_s, encbody = body.split(",",3)
        assert v0_s == "v0"
        pubkey = util.from_ascii(pubkey_s, "pk0-", encoding="base32")
        nonce = util.from_ascii(nonce_s, encoding="base32")
        assert len(pubkey) == crypto_box_PUBLICKEYBYTES
        assert len(nonce) == crypto_box_NONCEBYTES
        return (pubkey_s, pubkey, nonce, encbody)


    # main request-execution handler

    def process_request(self, msg, from_vatid):
        # really, you should ignore from_vatid
        log.msg("PROCESS %s" % (msg,))
        command = str(msg["command"])
        if command == "execute":
            memid = str(msg["memid"])
            powid = urbject.create_power_for_memid(self.db, memid)
            i = urbject.Invocation(self.db, msg["code"], powid)
            i.invoke(msg["args_json"], "{}", from_vatid)
            return
        if command == "invoke":
            urbjid = str(msg["urbjid"])
            u = urbject.Urbject(self.db, urbjid)
            u.invoke(msg["args_json"], msg["args_clist_json"], from_vatid)
            return
        pass


    # debug / CLI tools, triggered by 'poke'

    def send_execute(self, vatid, memid, code, args):
        msg = {"command": "execute",
               "memid": memid,
               "code": code,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps({})}
        self.send_message(vatid, json.dumps(msg))

    def send_invoke(self, vatid, urbjid, args):
        msg = {"command": "invoke",
               "urbjid": urbjid,
               "args_json": json.dumps(args),
               "args_clist_json": json.dumps({})}
        self.send_message(vatid, json.dumps(msg))

    def poke(self, body):
        if body.startswith("send "):
            cmd, vatid = body.strip().split()
            self.send_message(vatid, json.dumps({"command": "hello"}))
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
        self.trigger_inbound()
        self.trigger_outbound()
        return "I am poked"
