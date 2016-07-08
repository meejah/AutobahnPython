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

from functools import partial

from autobahn.twisted.multisocket import SwitchableProtocol
from autobahn.twisted.multisocket import SwitchableProtocolFactory
from autobahn.twisted.multisocket import raw_socket_predicate
from autobahn.twisted.multisocket import http11_predicate
from autobahn.twisted.multisocket import websocket_predicate

from autobahn.twisted.rawsocket import WampRawSocketServerFactory
from autobahn.twisted.websocket import WebSocketServerFactory
from autobahn.twisted.websocket import WebSocketServerProtocol

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

    # 3 different protocols we might switch between
    website_factory = Site(File('.'))
    websocket_factory = WebSocketServerFactory(u"ws://127.0.0.1:8080/ws")
    websocket_factory.protocol = MyWebSocketServerProtocol
    rawsocket_factory = WampRawSocketServerFactory(lambda: None)  # won't work, but ...

    # order matters!
    factory = SwitchableProtocolFactory()
    factory.add_protocol(raw_socket_predicate, rawsocket_factory)
    factory.add_protocol(partial(websocket_predicate, b'/ws'), websocket_factory)
    factory.add_protocol(http11_predicate, website_factory)

    reactor.listenTCP(8080, factory)
    reactor.run()
