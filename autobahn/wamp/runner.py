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

from __future__ import absolute_import, print_function

## XXX trying to factor out common ApplicationRunner stuff for
## asyncio/twisted

from types import StringType, ListType
from functools import wraps
import itertools
import json
import six
import txaio

from autobahn.wamp import transport
from autobahn.wamp.exception import TransportLost
from autobahn.websocket.protocol import parseWsUrl

# XXX move to transport? protocol
# XXX should at least move to same file as the "connect_to" things?
class Connection(object):
    """This represents configuration of a protocol and transport to make
    a WAMP connection to particular endpoints.

     - a WAMP protocol is "websocket" or "rawsocket"
     - the transport is TCP4, TCP6 (with or without TLS) or Unix socket.
     - ``.protocol`` is a "native" objects. That is, it might be
       autobahn.twisted.wamp.WampWebSocketClientProtocol if you're
       using Twisted (and a websocket protocol)

    This class handles the lifecycles of the underlying
    session/protocol pair. To get notifications of connection /
    disconnect and join / leave, add listeners on the underlying
    ISession object (``.session``)

    If :class:`ApplicationRunner
    <autobahn.twisted.wamp.ApplicationRunner` API is too high-level
    for your use-case, Connection lets you set up your own logging,
    call ``reactor.run()`` yourself, etc. ApplicationRunner in fact
    simply uses Connection internally. ApplicationRunner is the
    recommended API.

    :ivar protocol: current protocol instance, or ``None``
    :type protocol: tx:`twisted.internet.interfaces.IProtocol` or ``BaseProtocol`` subclass

    :ivar session: current ApplicationSession instance, or ``None``
    :type session: class:`autobahn.wamp.protocol.ApplicationSession` subclass

    :ivar connect_count: how many times we've successfully connected
        ("connected" at the transport level, *not* WAMP session "onJoin"
        level)
    :type connect_count: int

    :ivar attempt_count: how many times we've attempted to connect
    :type attempt_count: int

    """

    # XXX I decided to pass a actualy "session" instance (instead of
    # session_factory) so that adding listeners is easier, and because
    # it only ever got called once anyway.
    def __init__(self, session, transports, loop=None):
        """
        :param session: an ApplicationSession (or subclass) instance.

        :param transports: a list of dicts configuring available
            transports. See :meth:`autobahn.wamp.transport.check` for
            valid keys
        :type transports: list (of dicts)

        :param loop: reactor/event-loop instance (or None for a default one)
        :type loop: IReactorCore (Twisted) or EventLoop (asyncio)
        """

        assert(type(realm) == six.text_type)

        # public state (part of the API)
        self.protocol = None
        self.session = session
        self.connect_count = 0
        self.attempt_count = 0

        # private state / configuration
        self._connecting = None  # a Deferred/Future while connecting
        self._done = None  # a Deferred/Future that fires when we're done

        # generator for the next transport to try
        self._transport_gen = itertools.cycle(transports)

        # figure out which connect_to implementation we need
        if txaio.using_twisted:
            from autobahn.twisted.wamp import connect_to
        else:
            from autobahn.asyncio.wamp import connect_to
        self._connect_to = connect_to

        # the reactor or asyncio event-loop
        self._loop = loop

    def open(self):
        """
        Starts connecting (possibly also re-connecting, if configured) and
        returns a Deferred/Future that fires (with None) only after
        the session disconnects.

        This future will fire with an error if we:

          1. can't connect at all, or;
          2. connect, but the connection closes uncleanly
        """

        if self._connecting is not None:
            raise RuntimeError("Already connecting.")

        # XXX for now, all we look at is the first transport! ...this
        # will get fixed with retry-logic
        transport_config = next(self._transport_gen)
        # we check in the ctor, but only if it was a list; so we MUST
        # double-check the configuration here in case we had an
        # iterator.
        transport.check(transport_config, listen=False)

        # XXX sort of a philosophical question here -- do we
        # "let"/force the user to set .debug_app on their ISession by
        # their lonesome, or do we "overwrite" it with the
        # transport-config...? I'm trying to be a bit careful here and
        # not mess with it if it's already True...
        if not self.session.debug_app:
            self.session.debug_app = transport_config.get('debug_app', False)

        self.attempt_count += 1
        self._done = txaio.create_future()
        # this will resolve the _done future (good or bad)
        self.session.on('disconnect', self._on_disconnect)

        self._connecting = txaio.as_future(
            self._connect_to, self._loop, transport_config, self.session,
        )

        def on_error(fail):
            # XXX do we need to self._done.errback() here?
            try:
                nice_config = json.dumps(transport_config)
            except Exception:
                nice_config = str(transport_config)
            print("Error connecting to '{}': {}".format(nice_config, fail))
            fail.printTraceback()
            return fail

        def on_success(proto):
            self.connect_count += 1
            self.protocol = proto

        txaio.add_callbacks(self._connecting, on_success, on_error)
        return self._done

    def close(self):
        """
        Nicely close the session and/or transport. Returns a
        Deferred/Future that callbacks (with None) when we've closed
        down.

        Does nothing if the connection is already closed.
        """

        if self.session is not None:
            return self.session.leave()

        elif self.protocol:
            try:
                if txaio.using_twisted:
                    self.protocol.close()
                else:
                    self.protocol.lost_connection()
                return self.protocol.is_closed

            except TransportLost:
                # mimicing JS API, but...
                # XXX is this really an error? could just ignore it ...
                # or should provide ".is_open()" so you can avoid errors :/
                #raise RuntimeError('Connection already closed.')
                f = txaio.create_future()
                txaio.resolve(f, None)
                return f

    def _on_disconnect(self, reason):
        if reason == 'closed':
            self._done.callback(None)
        else:
            self._done.errback(Exception('Transport disconnected uncleanly'))
        self._connecting = None
        self._done = None

    def __str__(self):
        return "<Connection session={} protocol={} attempts={} connected={}>".format(
            self.session.__class__.__name__, self.protocol.__class__.__name__,
            self.attempt_count, self.connect_count)


class _ApplicationRunner(object):
    """
    Internal use.

    This is a common base-class between asyncio and Twisted; you
    should use one of the framework-specific subclasses:

    - autobahn.twisted.wamp.ApplicationRunner
    - autobahn.twisted.asyncio.ApplicationRunner
    """

    # XXX FIXME debug, debug_wamp etc. If we want to keep something
    # similar, put it in the transport config?
    def __init__(self, url_or_transports, realm, extra=None,
                 debug=False, debug_wamp=False, debug_app=False):
        """
        :param realm: The WAMP realm to join the application session to.
        :type realm: unicode

        :param url_or_transports:
            an iterable of dicts, each one configuring WAMP transport
            options, possibly including an Endpoint to connect
            to. WebSocket connections can implicitly derive a TCP4
            endpoint from the URL (and 'websocket' is the default
            type), so a websocket connection can be simply:
            ``transports={"url": "ws://demo.crossbar.io/ws"}``.

            If you pass a single string instead of an iterable, it is
            treated as a WebSocket URL and a single TCP4 transport is
            automatically created.
        :type url_or_transports: iterable (of dicts)

        :param extra: Optional extra configuration to forward to the
            application component.
        :type extra: any object

        :param debug: Turn on low-level debugging.
        :type debug: bool

        :param debug_wamp: Turn on WAMP-level debugging.
        :type debug_wamp: bool

        :param debug_app: Turn on app-level debugging.
        :type debug_app: bool
        """

        self.realm = realm
        self.extra = extra or dict()
        self.debug = debug
        self.debug_wamp = debug_wamp
        self.debug_app = debug_app

        if type(url_or_transports) in [StringType, six.text_type]:
            # XXX emit deprecation-warning? is it really deprecated?
            _, host, port, _, _, _ = parseWsUrl(url_or_transports)
            self.transports = [{
                "type": "websocket",
                "url": unicode(url_or_transports),
                "endpoint": {
                    "type": "tcp",
                    "host": host,
                    "port": port,
                }
            }]
        else:
            # XXX shall we also handle "passing a single dict" instead of 1-entry list?
            self.transports = url_or_transports

        # validate the transports we have ... but not if they're an
        # iterable. this gives feedback right away for invalid
        # transports if you passed a list, but lets you pass a
        # generator etc. instead if you want
        if type(self.transports) is ListType:
            for cfg in self.transports:
                transport.check(cfg, listen=False)

    def run(self, session_factory, **kw):
        raise RuntimeError("Subclass should override .run()")

