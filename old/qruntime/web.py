import os, json
from twisted.application import service, strports
from twisted.web import server, static, resource, http
from twisted.python import log
from .util import makeid, parse_spid

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
        self._server = server

    def render_POST(self, request):
        msg = request.content.read()
        resp = self._server.inbound_message(msg)
        return resp

class Poke(resource.Resource):
    def __init__(self, executor):
        resource.Resource.__init__(self)
        self._executor = executor

    def render_GET(self, request):
        return self._executor.poke("")

    def render_POST(self, request):
        body = request.content.read()
        return self._executor.poke(body)

class API(resource.Resource):
    def __init__(self, control, db, executor):
        resource.Resource.__init__(self)
        self.control = control
        self.db = db
        self.executor = executor

    def render_POST(self, request):
        r = json.loads(request.content.read())
        if not r["token"] in self.control.get_tokens():
            request.setResponseCode(http.UNAUTHORIZED, "bad token")
            return "Invalid token"
        method = str(r["method"])
        args = r["args"]
        c = self.db.cursor()
        data = None
        text = "unknown query"
        if method == "webport":
            c.execute("SELECT `webport` FROM `node`")
            text = c.fetchone()[0]
        elif method == "url":
            c.execute("SELECT `url` FROM `vat_urls`")
            text = c.fetchone()[0]
        elif method == "vatid":
            c.execute("SELECT `vatid` FROM `vat_urls`")
            text = c.fetchone()[0]
        elif method == "sendMessage":
            vatid, urbjid = parse_spid(args["to"])
            self.executor.send_invoke(vatid, urbjid, args["args"])
            text = "ok"
        elif method == "getAllObjects":
            c.execute("SELECT `urbjid` FROM `urbjects`")
            data = {"objects": [{"urbjid": r[0],
                                 #"petname": XXX,
                                 }
                                for r in c.fetchall()]}
        elif method == "getObjectGraph":
            data = {"graph": self.executor.get_object_graph()}
        else:
            raise ValueError("Unknown method '%s'" % method)
        if data is not None:
            return json.dumps(data)
        return json.dumps({"text": str(text)})

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
            return "Please use 'qrt open' to get to the control panel\n"
        nonce = request.args["nonce"][0]
        c = self.db.cursor()
        c.execute("SELECT nonce FROM webui_initial_nonces")
        nonces = [str(row[0]) for row in c.fetchall()]
        if nonce not in nonces:
            return ("Sorry, that nonce is expired or invalid,"
                    " please run 'qrt open' again\n")
        # good nonce, single-use
        c.execute("DELETE FROM webui_initial_nonces WHERE nonce=?", (nonce,))
        # this token lasts as long as the node is running: it is cleared at
        # startup
        token = makeid()
        c.execute("INSERT INTO `webui_access_tokens` VALUES (?)", (token,))
        self.db.commit()
        request.setHeader("content-type", "text/html")
        return read_media("login.html") % token

    def render_POST(self, request):
        token = request.args["token"][0]
        if token not in self.get_tokens():
            request.setHeader("content-type", "text/plain")
            return ("Sorry, this session token is expired,"
                    " please run 'qrt open' again\n")
        return read_media("control.html") % {"token": token}


class Root(resource.Resource):
    # child_FOO is a nevow thing, not in twisted.web.resource thing
    def __init__(self, db):
        resource.Resource.__init__(self)
        self.putChild("", static.Data("Hello\n", "text/plain"))
        self.putChild("media", static.File(MEDIA_DIRNAME))

class WebPort(service.MultiService):
    def __init__(self, basedir, node, db, executor):
        service.MultiService.__init__(self)
        self.basedir = basedir
        self.node = node
        self.db = db

        root = Root(db)

        # deliver messages to Server
        self.db.cursor().execute("DELETE FROM `webui_access_tokens`")
        self.db.commit()
        c = Control(db)
        capi = API(c, db, executor)
        c.putChild("api", capi)
        root.putChild("control", c)

        mi = MessageInput(node.server)
        root.putChild("messages", mi)
        root.putChild("poke", Poke(node.server.executor))

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
                    self.node._debug_webport = got_port
                    pieces[1] = str(got_port)
                    new_webport = ":".join(pieces)
                    self.node.set_node_config("webport", new_webport)
                except:
                    log.err()
                return port
            d.addCallback(_ready)
