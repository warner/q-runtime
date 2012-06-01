import os.path
import unittest
import collections
import json

from .. import invitation
from ..base32 import b2a
from ..client import Client
from .. import database
from ..scripts.create_node import create_node
from ..netstring import split_netstrings

class Outbound(unittest.TestCase):
    def test_create(self):
        code_ascii = b2a("code_binary")
        self.failUnlessEqual(b2a(invitation.get_hmac_key(code_ascii)),
                             "fvyuhvbg567wpixb5lzodtkvhpmfccwdrlp5a6zf7vvvqvlhhshq")
        self.failUnlessEqual(invitation.get_sender_address(code_ascii),
                             "channel-ihraxtbpsuxoohiuzjy646zkk5bh25e7gpyhwtpessv2ywn46bvq")

        h1, m1 = invitation.pack_messages(code_ascii, "1", "hello world")
        m2 = invitation.unpack_messages(code_ascii, h1, m1)
        self.failUnlessEqual(list(m2), ["1", "hello world"])
        wrong_code = b2a("wrong code")
        self.failUnlessRaises(ValueError,
                              invitation.unpack_messages, wrong_code, h1, m1)

        otherh,otherm = invitation.pack_messages(code_ascii, "different msg")
        self.failUnlessRaises(ValueError,
                              invitation.unpack_messages, code_ascii,
                              otherh, m1)

def testfilepath(*names):
    expanded = []
    for n in names:
        if isinstance(n, (tuple,list)):
            expanded.extend(list(n))
        else:
            expanded.append(n)
    names = expanded
    for i in range(1,len(names)):
        dirname = os.path.join(*names[:i])
        if not os.path.isdir(dirname):
            os.mkdir(dirname)
    return os.path.abspath(os.path.join(*names))

class Nexus:
    def __init__(self):
        self.subscriptions = collections.defaultdict(set)
    def send(self, c, m):
        messages = split_netstrings(m)
        if messages[0] == "subscribe":
            self.subscriptions[messages[1]].add(c)
        elif messages[0] == "send":
            for c_to in self.subscriptions[messages[1]]:
                c_to.message_received(c, messages)
        else:
            raise ValueError("unrecognized command %s" % messages[0])

class FakeClient(Client):
    nexus = None
    def maybe_send_messages(self):
        if not self.nexus:
            return
        while self.pending_messages:
            m = self.pending_messages.popleft()
            self.nexus.send(self, m)
    def message_received(self, fromwho, messages):
        Client.message_received(self, fromwho, messages)
        self.log.append((fromwho, messages))
    def add_addressbook_entry(self, petname, data, localdata):
        self.book.append( (petname,json.loads(data),json.loads(localdata)) )

class Roundtrip(unittest.TestCase):
    def mkfile(self, *names):
        return testfilepath("_test", *names)

    def create_clients(self, *names):
        base = os.path.join("_test", *names)
        self.mkfile(names, "dummy")
        create_node({"basedir": os.path.join(base, "c1"),
                     "webport": "tcp:0",
                     "relay": "tcp:host=localhost:port=0"})
        dbfile1 = self.mkfile(names, "c1", "toolbed.db")
        c1 = FakeClient(database.get_db(dbfile1)[1])

        create_node({"basedir": os.path.join(base, "c2"),
                     "webport": "tcp:0",
                     "relay": "tcp:host=localhost:port=0"})
        dbfile2 = self.mkfile(names, "c2", "toolbed.db")
        c2 = FakeClient(database.get_db(dbfile2)[1])

        c1.control_setProfileName("alice")
        c1.control_setProfileIcon("alice-icon")
        c2.control_setProfileName("bob")
        c2.control_setProfileIcon("bob-icon")

        n = Nexus()
        c1.nexus = n; c1.log = []; c1.book = []
        c2.nexus = n; c2.log = []; c2.book = []
        c1.maybe_send_messages(); c2.maybe_send_messages()
        self.c1 = c1
        self.c2 = c2
        self.n = n

    def test_contact(self):
        self.create_clients("invitation", "Roundtrip", "contact")
        c1,c2 = self.c1,self.c2
        c1.send_message_to_relay("send", c2.vk_s, "hello")
        self.failUnlessEqual(len(c2.log), 1)
        self.failUnlessEqual(c2.log[-1][0], c1)
        self.failUnlessEqual(c2.log[-1][1], ["send", c2.vk_s, "hello"])

    def test_invite(self):
        self.create_clients("invitation", "Roundtrip", "invite")
        c1,c2,n = self.c1,self.c2,self.n

        c1.control_sendInvitation("pet-bob")
        data = c1.control_getOutboundInvitationsJSONable()
        self.failUnlessEqual(len(data), 1)
        self.failUnlessEqual(data[0]["petname"], "pet-bob")
        code_ascii = data[0]["code"]

        # c1 should have subscribed to hear about its channel by now
        c1_channel = invitation.get_sender_address(code_ascii)
        self.failUnless(c1_channel in n.subscriptions)
        self.failUnlessEqual(n.subscriptions[c1_channel], set([c1]))

        # all protocol messages complete inside this call
        c2.control_acceptInvitation("pet-alice", code_ascii)

        self.failUnlessEqual(len(c1.book), 1)
        self.failUnlessEqual(c1.book[0][0], "pet-bob")
        d1 = c1.book[0][1]
        self.failUnlessEqual(sorted(d1.keys()),
                             sorted(["my-name", "my-icon", "my-pubkey"]))
        self.failUnlessEqual(d1["my-name"], "bob")
        self.failUnlessEqual(d1["my-icon"], "bob-icon")
        k1 = d1["my-pubkey"]
        d2 = c1.book[0][2]
        self.failUnlessEqual(sorted(d2.keys()),
                             sorted(["my-pubkey", "my-privkey"]))
        k2 = d2["my-pubkey"]

        self.failUnlessEqual(len(c2.book), 1)
        self.failUnlessEqual(c2.book[0][0], "pet-alice")
        d3 = c2.book[0][1]
        self.failUnlessEqual(sorted(d3.keys()),
                             sorted(["my-name", "my-icon", "my-pubkey"]))
        self.failUnlessEqual(d3["my-name"], "alice")
        self.failUnlessEqual(d3["my-icon"], "alice-icon")
        k3 = d3["my-pubkey"]
        d4 = c2.book[0][2]
        self.failUnlessEqual(sorted(d4.keys()),
                             sorted(["my-pubkey", "my-privkey"]))
        k4 = d4["my-pubkey"]

        self.failUnlessEqual(k1, k4)
        self.failUnlessEqual(k2, k3)
