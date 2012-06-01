import os, json
from twisted.application import service, strports
from twisted.web import server, static, resource, http
from twisted.python import log
from .nonce import make_nonce
from .netstring import split_netstrings

MEDIA_DIRNAME = os.path.join(os.path.dirname(__file__), "media")

def read_media(fn):
    f = open(os.path.join(MEDIA_DIRNAME,fn), "rb")
    #data = f.read().decode("utf-8")
    data = f.read()
    f.close()
    return data

class MessageInput(resource.Resource):
    def __init__(self, server):
        resource.Resource.__init__(self)
        self.server = server

    def render_POST(self, request):
        msg = request.content.read() # (pubkey, nonce, encbody) as netstrings
        pubkey, nonce, encbody = split_netstrings(msg)
        resp = self.server.inbound_message(pubkey, nonce, encbody)
        return resp

class Control(resource.Resource):
    def __init__(self, db):
        resource.Resource.__init__(self)
        self.db = db

    def get_tokens(self):
        c = self.db.cursor()
        c.execute("SELECT `token` FROM `webui_access_tokens`")
        return set([str(row[0]) for row in c.fetchall()])

    def render_GET(self, request):
        request.setHeader("content-type", "text/plain")
        if "nonce" not in request.args:
            return "Please use 'ssp open' to get to the control panel\n"
        nonce = request.args["nonce"][0]
        c = self.db.cursor()
        c.execute("SELECT nonce FROM webui_initial_nonces")
        nonces = [str(row[0]) for row in c.fetchall()]
        if nonce not in nonces:
            return ("Sorry, that nonce is expired or invalid,"
                    " please run 'ssp open' again\n")
        # good nonce, single-use
        c.execute("DELETE FROM webui_initial_nonces WHERE nonce=?", (nonce,))
        # this token lasts as long as the node is running: it is cleared at
        # startup
        token = make_nonce()
        c.execute("INSERT INTO `webui_access_tokens` VALUES (?)", (token,))
        self.db.commit()
        request.setHeader("content-type", "text/html")
        return read_media("login.html") % token

    def render_POST(self, request):
        token = request.args["token"][0]
        if token not in self.get_tokens():
            request.setHeader("content-type", "text/plain")
            return ("Sorry, this session token is expired,"
                    " please run 'ssp open' again\n")
        return read_media("control.html") % {"token": token}


class Root(resource.Resource):
    # child_FOO is a nevow thing, not in twisted.web.resource thing
    def __init__(self, db):
        resource.Resource.__init__(self)
        self.putChild("", static.Data("Hello\n", "text/plain"))
        self.putChild("media", static.File(MEDIA_DIRNAME))

class WebPort(service.MultiService):
    def __init__(self, basedir, node, db):
        service.MultiService.__init__(self)
        self.basedir = basedir
        self.node = node
        self.db = db

        root = Root(db)

        c = Control(db)
        root.putChild("control", c)

        # deliver messages to Server
        self.db.cursor().execute("DELETE FROM `webui_access_tokens`")
        self.db.commit()
        mi = MessageInput(node.server)
        c.putChild("messages", mi)

        site = server.Site(root)
        webport = str(node.get_node_config("webport"))
        self.port_service = strports.service(webport, site)
        self.port_service.setServiceParent(self)

    def startService(self):
        service.MultiService.startService(self)

        # now update the webport, if we started with port=0 . This is gross.
        webport = str(self.node.get_node_config("webport"))
        pieces = webport.split(":")
        if pieces[0:2] == ["tcp", "0"]:
            d = self.port_service._waitingForPort
            def _ready(port):
                try:
                    got_port = port.getHost().port
                    pieces[1] = str(got_port)
                    new_webport = ":".join(pieces)
                    self.node.set_node_config("webport", new_webport)
                except:
                    log.err()
                return port
            d.addCallback(_ready)