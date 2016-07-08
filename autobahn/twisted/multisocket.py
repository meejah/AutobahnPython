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

from __future__ import absolute_import

import txaio
txaio.use_twisted()

from twisted.internet.protocol import Factory, Protocol

__all__ = (
    'MultiSocketServerProtocol',
    'MultiSocketServerFactory',
)


class MultiSocketServerProtocol(Protocol):
    """
    """
    log = txaio.make_logger()

    def __init__(self, factory, addr):
        self._factory = factory
        self._addr = addr
        self._proto = None
        self._data = b''

    def connectionMade(self):
        print("foo")

    def dataReceived(self, data):

        if self._proto:
            # we already determined the actual protocol to speak. just forward received data
            self._proto.dataReceived(data)
        else:
            if data[0] == b'\x7F':
                # RawSocket
                if not self._factory._rawsocket_factory:
                    self.log.warn('client wants to talk RawSocket, but we have no factory configured for that')
                    self.transport.loseConnection()
                else:
                    self._proto = self._factory._rawsocket_factory.buildProtocol(self._addr)
                    self._proto.connectionMade()
                    self._proto.dataReceived(data)
            else:
                # WebSocket or Web
                self._data += data

                request_line_end = self._data.find(b'\x0d\x0a')
                request_line = self._data[:request_line_end]

                rl = request_line.split()
                if len(rl) != 3:
                    self.transport.loseConnection()

                request_url = rl[1].strip()

                self.log.debug('got HTTP request for URL {request_url}', request_url=request_url)

                # GET /ws HTTP/1.1

                if self._factory._websocket_factory_map:
                    for url, websocket_factory in self._factory._websocket_factory_map.items():
                        if request_url.startswith(url):
                            self._proto = websocket_factory.buildProtocol(self._addr)
                            break

                if not self._proto and self._factory._website_factory:
                    self._proto = self._factory._website_factory.buildProtocol(self._addr)

                self._proto.transport = self.transport
                #if hasattr(self._proto, 'channel'):
                self._proto.channel.transport = self.transport

                self._proto.connectionMade()
                self._proto.dataReceived(self._data)
                self._data = None

    def connectionLost(self, reason):
        if self._proto:
            self._proto.connectionLost(reason)


class MultiSocketServerFactory(Factory):
    """
    """

    def __init__(self, rawsocket_factory=None, websocket_factory_map=None, website_factory=None):
        """
        twisted.web.server.Site
        """
        self._rawsocket_factory = rawsocket_factory
        self._websocket_factory_map = websocket_factory_map
        self._website_factory = website_factory

    def buildProtocol(self, addr):
        proto = MultiSocketServerProtocol(self, addr)
        return proto
