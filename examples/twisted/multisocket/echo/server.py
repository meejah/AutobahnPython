###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) Tavendo GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################

from autobahn.twisted.multisocket import MultiSocketServerProtocol, \
    MultiSocketServerFactory

#from autobahn.twisted.rawsocket import RawSocketServerProtocol, \
#    RawSocketServerFactory

from autobahn.twisted.websocket import WebSocketServerProtocol, \
    WebSocketServerFactory

from twisted.web.server import Site
from twisted.web.static import File


class MyWebSocketServerProtocol(WebSocketServerProtocol):

    def onConnect(self, request):
        print("Client connecting: {0}".format(request.peer))

    def onOpen(self):
        print("WebSocket connection open.")

    def onMessage(self, payload, isBinary):
        if isBinary:
            print("Binary message received: {0} bytes".format(len(payload)))
        else:
            print("Text message received: {0}".format(payload.decode('utf8')))

        # echo back message verbatim
        self.sendMessage(payload, isBinary)

    def onClose(self, wasClean, code, reason):
        print("WebSocket connection closed: {0}".format(reason))


if __name__ == '__main__':

    import txaio
    txaio.use_twisted()

    from twisted.internet import reactor

    txaio.start_logging(level='debug')

    website_factory = Site(File('.'))

    websocket_factory = WebSocketServerFactory(u"ws://127.0.0.1:8080/ws")
    websocket_factory.protocol = MyWebSocketServerProtocol

    multisocket_factory = MultiSocketServerFactory(websocket_factory_map={b'/ws': websocket_factory}, website_factory=website_factory)

    reactor.listenTCP(8080, multisocket_factory)
    reactor.run()
