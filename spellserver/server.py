import re
import collections
import weakref
import json
from twisted.application import service
from twisted.python import log
from twisted.internet import protocol, reactor
from twisted.protocols import basic
import nacl
from .netstring import make_netstring, split_netstrings
from . import invitation, util


class Server(service.MultiService):
    def __init__(self, db, pubkey, privkey):
        service.MultiService.__init__(self)
        self.db = db
        c = self.db.cursor()

        self.pubkey = pubkey
        self.privkey = privkey

        # resending messages: we use Waterken's "retry-forever" style.
        # Ideally, we'd like messages to any given Vat to be resent on an
        # exponential backoff timer: the first time we try to send a message
        # and get a rejected connection, we should wait 5 seconds before
        # trying again, then 10 seconds, then 20, etc, capping the backoff at
        # an hour or two. In addition, each time a new message is added to
        # the queue for that Vat, we should make an immediate attempt (but
        # not affect the timer). Any success resets the timer. The pending
        # (unACKed) messages live in the database. So what this will really
        # want is something that looks at the DB, computes a next-retry-time
        # for each VatID that has pending messages, takes the minimum of
        # those times, then sets a timer to wake up at that point. Maybe the
        # whole retry schedule should be put in the DB, so if this server
        # sleeps through the attempts, it wakes up doing the slow-poll
        # instead of the fast-poll.

        # also, consider the differences between TCP connection failures and
        # delayed/lost ACKs. We actually care about the ACK. But we need to
        # give them a reasonable amount of time to receive and store the
        # message, especially for large messages. (scheduling a retry 5
        # seconds after we start sending a multi-minute message would be a
        # disaster). So, do an HTTP send, if it succeeds (i.e. the encrypted
        # response contains an ACK), then the message is retired. If and when
        # it fails, start the timer. (this allows Vats to stall forever, but
        # that's their perogative, and resending early to such a vat won't do
        # any good).

    # nonce management: we need to response

    def inbound_message(self, pubkey, nonce, encbody):
        assert len(pubkey)==nacl.crypto_box_PUBLICKEYBYTES, len(pubkey)
        assert len(nonce)==nacl.crypto_box_NONCEBYTES, len(nonce)
        nonce_number = int(hexlify(nonce), 16)
        c = self.db.cursor()
        c.execute("SELECT next_msgnum FROM inbound_msgnums LIMIT 1"
                  " WHERE from_vatid = ?", (pubkey,))
        (next_msgnum,) = c.fetchone()
        expected_nonce = self.make_nonce(next_msgnum, pubkey)
        # If the nonce is old, we remember processing this message, so just
        # ACK it. If the nonce is too new, signal an error: that either means
        # we've been rolled back, or they're sending nonces from the future.
        # If the nonce is just right, process the message.
        if nonce_number > expected_nonce:
            
            


        expected_nonce = self.parent.
        if self.check_inbound_nonce(pubkey, nonce_number):
            
        msg = nacl.crypto_box_open(encbody, nonce, pubkey, self.privkey)

    def make_nonce(self, msgnum, their_pubkey):
        if self.pubkey > their_pubkey:
            return 2*msgnum+1
        else:
            return 2*msgnum+0

    def check_inbound_nonce(self, vatid, nonce):

    def control_sendInvitation(self, petname):
        # in the medium-size code protocol, the invitation code I is just a
        # random string.
        print "sendInvitation", petname
        pk_s, sk_s = self.create_keypair()
        payload = {"my-name": self.control_getProfileName(),
                   "my-icon": self.control_getProfileIcon(),
                   # TODO: passing the icon as a data: URL is probably an
                   # attack vector, change it to just pass the data and have
                   # the client add the "data:" prefix
                   "my-pubkey": pk_s,
                   }
        forward_payload_data = json.dumps(payload).encode("utf-8")
        local_payload = {"my-pubkey": pk_s, "my-privkey": sk_s}
        local_payload_data = json.dumps(local_payload).encode("utf-8")
        invite = invitation.create_outbound(self.db, petname,
                                            forward_payload_data,
                                            local_payload_data)
        self.subscribe_to_all_pending_invitations()
        # when this XHR returns, the JS client will fetch the pending
        # invitation list and show the most recent entry
        return invite

    def subscribe_to_all_pending_invitations(self):
        for addr in invitation.addresses_to_subscribe(self.db):
            self.send_message_to_relay("subscribe", addr)
        # TODO: when called by startInvitation, it'd be nice to sync here: be
        # certain that the relay server has received our subscription
        # request, before returning to startInvitation and allowing the user
        # to send the invite code. If they stall for some reason, we might
        # miss the response.

    def control_cancelInvitation(self, invite):
        print "cancelInvitation", invite
        c = self.db.cursor()
        c.execute("DELETE FROM `outbound_invitations`"
                  " WHERE `petname`=? AND `code`=?",
                  (str(invite["petname"]), str(invite["code"])))
        self.db.commit()

    def control_acceptInvitation(self, petname, code_ascii):
        print "acceptInvitation", petname, code_ascii
        pk_s, sk_s = self.create_keypair()
        payload = {"my-name": self.control_getProfileName(),
                   "my-icon": self.control_getProfileIcon(), # see above
                   "my-pubkey": pk_s,
                   }
        reverse_payload_data = json.dumps(payload).encode("utf-8")
        local_payload = {"my-pubkey": pk_s, "my-privkey": sk_s}
        local_payload_data = json.dumps(local_payload).encode("utf-8")
        outmsgs = invitation.accept_invitation(self.db,
                                               petname, code_ascii,
                                               reverse_payload_data,
                                               local_payload_data)
        for outmsg in outmsgs:
            self.send_message_to_relay(*outmsg)

    def control_getOutboundInvitationsJSONable(self):
        return invitation.pending_outbound_invitations(self.db)

    def control_getAddressBookJSONable(self):
        c = self.db.cursor()
        c.execute("SELECT `petname`,`selfname`,`icon_data`,`their_pubkey`"
                  " FROM `addressbook`"
                  " ORDER BY `petname` ASC")
        data = [{ "petname": str(row[0]),
                  "selfname": str(row[1]),
                  "icon_data": str(row[2]),
                  "their_pubkey": str(row[3]),
                  }
                for row in c.fetchall()]
        return data
    def control_deleteAddressBookEntry(self, petname):
        c = self.db.cursor()
        c.execute("DELETE FROM `addressbook` WHERE `petname`=?", (petname,))
        self.db.commit()
        self.notify("address-book-changed", None)

    def control_subscribe_events(self, subscriber):
        self.subscribers[subscriber] = None
    def control_unsubscribe_events(self, subscriber):
        self.subscribers.pop(subscriber, None)
    def notify(self, what, data):
        print "NOTIFY", what, data
        for s in self.subscribers:
            msg = json.dumps({"message": data})
            s.event(what, msg) # TODO: eventual-send
