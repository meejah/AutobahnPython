from __future__ import absolute_import

## XXX trying to factor out common ApplicationRunner stuff for
## asyncio/twisted

from types import StringType
import six

from autobahn.wamp import transport


# XXX maybe more sense in wamp.transport.connect_to?
@inlineCallbacks
def connect_to(loop, transport_config, session_factory, realm, extra, on_error=None):
    """
    :param transport_config: dict containing valid client transport
    config (see :mod:`autobahn.wamp.transport`)

    :param session_factory: callable that takes a ComponentConfig and
    returns a new ISession instance (usually simply your
    ApplicationSession subclass)

    :param on_error: a callable that takes an Exception, called if we
    get an error connecting

    :returns: Deferred that callbacks with ... "Connection" instance?
    Nothing? .. after a connection has been made (not necessarily a
    WAMP session joined yet, however)
    """

    # factory for using ApplicationSession
    def create():
        try:
            session = session_factory(ComponentConfig(realm, extra))
            # XXX FIXME session.debug_app = self.debug_app
            return session

        except Exception as e:
            if on_error:
                on_error(e)
            else:
                log.err("Exception while creating session: {0}".format(e))
            raise

    transport_factory = _create_wamp_factory(loop, transport_config, create)
    proto = yield _connect_stream(loop, transport_config['endpoint'], transport_factory)

    # as the reactor/event-loop shuts down, we wish to wait until we've sent
    # out our "Goodbye" message; leave() returns a Deferred that
    # fires when the transport gets to STATE_CLOSED
    def cleanup():
        if hasattr(proto, '_session') and proto._session is not None:
            return proto._session.leave()
    reactor.addSystemEventTrigger('before', 'shutdown', cleanup)

    returnValue(proto)


class Connection(object):
    """
    This represents configuration of a protocol and transport to make
    a WAMP connection to particular endpoints.

     - a WAMP protocol is "websocket" or "rawsocket"
     - the transport is TCP4, TCP6 (with or without TLS) or Unix socket.

    This handles the lifecycles of the underlying transport/protocol
    pair, providing notifications of transitions.

    If :class:`ApplicationRunner <autobahn.twisted.wamp.ApplicationRunner`
    API is too high-level for your use-case, Connection lets you set
    up your own Twisted logging, call ``reactor.run()`` yourself,
    etc. ApplicationRunner in fact simply uses Connection internally.

    :ivar protocol: current protocol instance, or ``None``
    :type protocol: tx:`twisted.internet.interfaces.IProtocol`

    :ivar session: current ApplicationSession instance, or ``None``
    :type session: class:`autobahn.wamp.protocol.ApplicationSession` subclass

    :ivar connect_count: how many times we've successfully connected
        ("connected" at the transport level, *not* WAMP session "onJoin"
        level)
    """

    # XXX just make these strings for easier debugging? object() makes
    # it clear you have to use Connection.ERROR etc...

    # possible events that we emit; if adding one, add to
    # _event_listeners dict too
    ERROR = object()  #: callback gets Exception instance
    CREATE_SESSION = object()  #: callback gets ApplicationSession instance
    SESSION_LEAVE = object()  #: callback gets ApplicationSession instance
    CONNECTED = object()  #: callback gets IProtocol instance
    CLOSED = object()  #: callback gets reason (string) + details (CloseDetails instance)
                       #: reason is "lost", "closed" or "unreachable"

    def __init__(self, session_factory, transports, realm, extra):
        """
        :param session_factory: callable that takes a ComponentConfig and
            returns a new ApplicationSession subclass

        :param transports: a list of dicts configuring available
            transports. See :meth:`autobahn.wamp.transport.check` for
            valid keys
        :type transports: list of dicts

        :param realm: the realm to join
        :type realm: unicode

        :param extra: an object available as 'self.config.extra' in
            your ApplicationSession subclass. Can be anything, e.g
            dict().
        """

        # state (also part of the API)
        self.protocol = None
        self.session = None
        self.connect_count = 0
        self.attempt_count = 0

        # private state + config
        self._session_factory = session_factory
        self._realm = realm
        self._extra = extra

        # our event listeners
        self._event_listeners = {
            self.ERROR: [],
            self.CREATE_SESSION: [],
            self.SESSION_LEAVE: [],
            self.CONNECTED: [],
            self.CLOSED: [],
        }

        def transport_gen():
            while True:
                for tr in transports:
                    yield tr
        self._transport_gen = transport_gen()

    def add_event(self, event_type, cb):
        """
        Add a listener for the given ``event_type``; the callback ``cb``
        takes a single argument, whose value depends on the
        event.

        XXX should CLOSED be an exception and take CloseDetails also?
        but only when "closed" state?! (like AutobahnJS)

        Valid events are:

         - ``ERROR``: called with Exception whenever a connect() attempt fails
         - ``CREATE_SESSION``: called with ApplicationSession instance upon session creation
         - ``SESSION_LEAVE``: called with ApplicationSession instance when session leaves
         - ``CONNECTED``: called with IProtocol instance when transport connects
         - ``CLOSED``: called when transport disconnects with "unreachable", "lost", or "closed"
        """
        try:
            self._event_listeners[event_type].append(cb)
        except KeyError:
            raise ValueError("Unknown event-type '{}'".format(event_type))

    def remove_event(self, event_type, cb):
        """
        Stop listening.
        """
        try:
            self._event_listeners[event_type].remove(cb)
        except ValueError:
            msg = "Callback '{}' not found for event '{}'"
            raise ValueError(msg.format(cb, event_type))
        except KeyError:
            msg = "No listeners for event '{}'"
            raise ValueError(msg.format(event_type))

    # XXX actually, just this thing needs custom implementation for asyncio vs. Twisted?

    @inlineCallbacks
    def connect(self, loop):
        """
        Starts connecting (possibly also re-connecting) and returns a
        Deferred that fires (with None) when we first connect.
        """
        # XXX for now, all we look at is the first transport! ...this
        # will get fixed with retry-logic

        try:
            transport_config = next(self._transport_gen)
            self.protocol = yield connect_to(
                loop,
                transport_config,
                self._create_session,
                self._realm,
                self._extra,
            )

        except Exception as e:
            log.err("Error connecting to '{}': {}".format(
                json.dumps(transport_config), e))
            # seems redundant but for retry-logic, we can only
            # Deferred-error on the very first connect_to() attempt
            self._fire_event(self.ERROR, e)
            raise

        # "listen" for connectionLost
        orig = self.protocol.transport.connectionLost

        @wraps(self.protocol.transport.connectionLost)
        def wrapper(*args, **kw):
            rtn = orig(*args, **kw)
            # Failure instance is first arg
            f = args[0]
            if self.connect_count == 0:
                self._fire_event(self.CLOSED, "unreachable")
            else:
                if isinstance(f.value, ConnectionDone):
                    self._fire_event(self.CLOSED, "closed")
                else:
                    # XXX javascrpt allows this to return
                    # "false" to cancel reconnection
                    self._fire_event(self.CLOSED, "lost")
            self.protocol = None
            return rtn
        self.protocol.transport.connectionLost = wrapper

    def _fire_event(self, evt, *args, **kw):
        """
        Internal helper. MUST NOT throw Exceptions
        """
        for cb in self._event_listeners[evt]:
            try:
                cb(*args, **kw)
            except Exception as e:
                log.err("While running callback '{}' for '{}': {}".format(
                    cb, self._event_to_name(evt), e))

    def _event_to_name(self, evt):
        for (k, v) in self.__class__.__dict__.items():
            if v == evt:
                return k
        return 'unknown'

    def _create_session(self, cfg):
        self.session = self._session_factory(cfg)
        self._fire_event(self.CREATE_SESSION, self.session)
        self.connect_count += 1

        # "listen" for onLeave
        on_leave = self.session.onLeave

        @wraps(self.session.onLeave)
        def wrapper(*args, **kw):
            # callback with the Failure instance
            rtn = on_leave(*args, **kw)
            self._fire_event(self.SESSION_LEAVE, self.session)
            self.session = None  # must come *after* callbacks
            return rtn
        self.session.onLeave = wrapper

        # "listen" for disconnect/leave so we know if we should keep
        # re-trying or not ...
        # this means: disconnect() and we keep reconnecting; leave() and we stop
        leave = self.session.leave
        @wraps(self.session.leave)
        def wrapper(*args, **kw):
            rtn = leave(*args, **kw)
            self._shutting_down = True
            return rtn
        self.session.leave = wrapper

        return self.session

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

    def __init__(self, url_or_transports, realm, extra=None,
                 ssl=None,  # kind-of related to transports too ...
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

        XXX FIXME logically, "TLS stuff" should go in the transports; what
        to do with ssl= arg? for now we'll just stuff it automagically
        in every transport def'n

        :type transports: iterable (of dicts)

        :param extra: Optional extra configuration to forward to the
            application component.
        :type extra: dict

        :param debug: Turn on low-level debugging.
        :type debug: bool

        :param debug_wamp: Turn on WAMP-level debugging.
        :type debug_wamp: bool

        :param debug_app: Turn on app-level debugging.
        :type debug_app: bool

        :param ssl: (Optional). If specified this should be an
            instance suitable to pass as ``sslContextFactory`` to
            :class:`twisted.internet.endpoints.SSL4ClientEndpoint`` such
            as :class:`twisted.internet.ssl.CertificateOptions`. Leaving
            it as ``None`` will use the result of calling Twisted's
            :meth:`twisted.internet.ssl.platformTrust` which tries to use
            your distribution's CA certificates.
        :type ssl: :class:`twisted.internet.ssl.CertificateOptions`
        """

        self.realm = realm
        self.extra = extra or dict()
        self.debug = debug
        self.debug_wamp = debug_wamp
        self.debug_app = debug_app
        self.make = None
        self.ssl = ssl
        self._protocol = None
        self._session = None
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

        # validate the transports we have
        for cfg in self.transports:
            transport.check(cfg, listen=False)
            cfg['endpoint']['ssl'] = ssl  # HACK FIXME

    def run(self, session_factory, **kw):
        raise RuntimeError("Subclass should override .run()")

