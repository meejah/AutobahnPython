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

import sys
import inspect
from types import StringType
from functools import wraps
import json

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twisted.internet.error import ConnectionDone

from autobahn.wamp import protocol
from autobahn.wamp.types import ComponentConfig
from autobahn.websocket.protocol import parseWsUrl
from autobahn.twisted.util import sleep
from autobahn.twisted.websocket import WampWebSocketClientFactory
from autobahn.twisted.rawsocket import WampRawSocketClientFactory
from autobahn.wamp import transport

import six
import txaio
txaio.use_twisted()


__all__ = [
    'ApplicationSession',
    'ApplicationSessionFactory',
    'ApplicationRunner',
    'Application',
    'Service'
]

try:
    from twisted.application import service
except (ImportError, SyntaxError):
    # Not on PY3 yet
    service = None
    __all__.pop(__all__.index('Service'))


class ApplicationSession(protocol.ApplicationSession):
    """
    WAMP application session for Twisted-based applications.
    """

    def onUserError(self, e, msg):
        """
        Override of wamp.ApplicationSession
        """
        # see docs; will print currently-active exception to the logs,
        # which is just what we want.
        log.err(e)
        # also log the framework-provided error-message
        log.err(msg)


class ApplicationSessionFactory(protocol.ApplicationSessionFactory):
    """
    WAMP application session factory for Twisted-based applications.
    """

    session = ApplicationSession
    """
    The application session class this application session factory
    will use. Defaults to :class:`autobahn.twisted.wamp.ApplicationSession`.
    """


# XXX this would need an asyncio vs Twisted impl if going that route ...
def _connect_stream(reactor, cfg, wamp_transport_factory):
    """
    Internal helper.

    Connects the given wamp_transport_factory to a stream endpoint, as
    determined from the cfg that's passed in (which should be just the
    "endpoint" part). Returns Deferred that fires with IProtocol
    """

    if isinstance(cfg, six.text_type):
        client = clientFromString(cfg)

    # XXX could accept an actual endpoint instance, too/instead?

    else:
        if cfg['type'] == 'unix':
            if cfg['ssl']:
                raise RuntimeError("No TLS in Unix sockets")
            from twisted.internet.endpoints import UNIXClientEndpoint
            client = UNIXClientEndpoint(reactor, cfg['path'])

        elif cfg['type'] == 'tcp':
            if cfg.get('version', 4) == 4:
                if 'ssl' in cfg and 'tls' in cfg:
                    raise RuntimeError("'ssl' and 'tls' are mutually exclusive "
                                       "in endpoint configuration")
                if cfg['ssl']:
                    # ssl= should be a "native" Twisted TLS configuration,
                    # that is a :tx:`twisted.internet.ssl.ContextFactory`
                    context_factory = cfg['ssl']
                    from twisted.internet.endpoints import SSL4ClientEndpoint
                    assert context_factory is not None
                    client = SSL4ClientEndpoint(reactor, cfg['host'], cfg['port'],
                                                cfg['ssl'])
                else:
                    from twisted.internet.endpoints import TCP4ClientEndpoint
                    client = TCP4ClientEndpoint(reactor, cfg['host'], cfg['port'])
            else:
                if cfg['ssl']:
                    raise RuntimeError("FIXME: TLS over IPv6")
                from twisted.internet.endpoints import TCP6ClientEndpoint
                client = TCP6ClientEndpoint(reactor, cfg['host'], cfg['port'])
        else:
            raise RuntimeError("Unknown type='{}'".format(cfg['type']))

    print("Connecting", client)
    return client.connect(wamp_transport_factory)


# needs custom asycio vs Twisted (because where the imports come from)
# -- or would have to do "if txaio.using_twisted():" etc switch-type
# statement.
def _create_wamp_factory(reactor, cfg, session_factory):
    """
    Internal helper.

    This creates the appropriate protocol-factory (that implements
    tx:`IProtocolFactory <twisted.internet.interfaces.IProtocolFactory>`)

    XXX deal with debug/debug_wamp etcetc.
    """

    # type in ['websocket', 'rawsocket']
    create_instance = {
        "websocket": lambda: WampWebSocketClientFactory(session_factory, url=cfg['url']),
        "rawsocket": lambda: WampRawSocketClientFactory(session_factory),
    }
    return create_instance[cfg['type']]()


# XXX THINK move to transport.py?
# XXX can this be made generic by passing loop/reactor and using txaio?
@inlineCallbacks
def connect_to(reactor, transport_config, session_factory, realm, extra, on_error=None):
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

    transport_factory = _create_wamp_factory(reactor, transport_config, create)
    proto = yield _connect_stream(reactor, transport_config['endpoint'], transport_factory)

    # as the reactor shuts down, we wish to wait until we've sent
    # out our "Goodbye" message; leave() returns a Deferred that
    # fires when the transport gets to STATE_CLOSED
    def cleanup():
        if hasattr(proto, '_session') and proto._session is not None:
            return proto._session.leave()
    reactor.addSystemEventTrigger('before', 'shutdown', cleanup)

    returnValue(proto)


# XXX should be common between this and asyncio
def _create_retry_scheduler(cfg):
    """
    internal helper

    This returns a generator-function that, when called, will produce
    a new generator which yields subsequent delays for retries.
    """

    transport.check_retry(cfg)

    def retry_schedule():
        delay = cfg.get("initial_retry_delay", 1.5)
        max_retries = cfg.get("max_retries", 15)
        max_delay = cfg.get("max_retry_delay", 300)
        rate = cfg.get("retry_growth_rate", 1.5)
        # retry_delay_jitter
        attempts = 1
        while True:
            yield delay
            delay *= rate
            delay = min(delay, max_delay)
            attempts += 1
            if attempts > max_retries:
                break
    return retry_schedule


# XXX probably want IConnection to declare API (e.g. so asyncio one
# follows it as well)
# XXX we can probably make this common via txaio as well...
class Connection(object):
    """
    This represents configuration of a protocol and transport to make
    a WAMP connection to particular endpoints. Retry behavior can be
    configured also.

     - a WAMP protocol is "websocket" or "rawsocket"
     - the transport is TCP4, TCP6 (with or without TLS) or Unix socket.

    This handles the lifecycles of the underlying transport/protocol
    pair, providing notifications of transitions.

    If a retry configuration is provided, this class deals with
    reconnecting. So for example if a transport "went away", you would
    receive two CREATE_SESSION events as the WAMP session got
    re-started (and hence re-created). Thus, you should prefer
    accessing the session and protocol via `Connection.session` and
    `Connection.protocol`. These are ``None`` if the transport is not
    connected, or if the session has yet to be established.

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

    # possible events that we emit; if adding one, add to
    # _event_listeners dict too
    ERROR = object()  #: callback gets Exception instance
    CREATE_SESSION = object()  #: callback gets ApplicationSession instance
    SESSION_LEAVE = object()  #: callback gets ApplicationSession instance
    CONNECTED = object()  #: callback gets IProtocol instance
    CLOSED = object()  #: callback gets reason (string) + details (CloseDetails instance)
                       #: reason is "lost", "closed" or "unreachable"

    # XXX what about a "giving up now" event, mostly related to retry
    # / reconnection (i.e. this event would fire when this Connection
    # will no longer be trying to connect). ApplicationRunner would
    # use this to "reactor.stop()" and direct users of Connection can
    # do what they feel like. Maybe that's what ERROR should be
    # called, instead? So it gets None if there was no error
    # (i.e. .leave() was callled on the session) otherwise, Exception
    # instance

    def __init__(self, session_factory, transports, realm, extra, retry):
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

        :param retry: either None (no retrying) or a dict
            configurating retry logic see the documentation for
            :meth:`autobahn.wamp.transport.check_retry` for valid keys
        :type retry: dict
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

        # retry logic
        self._retry = None
        self._retry_scheduler = lambda: None
        self._retry_on_unreachable = False
        if retry is not None:
            self._retry_scheduler = _create_retry_scheduler(retry)
            self._retry = self._retry_scheduler()
            self._retry_on_unreachable = retry.get('retry_on_unreachable', False)
        self._shutting_down = False

        # our event listeners
        self._event_listeners = {
            self.ERROR: [],
            self.CREATE_SESSION: [],
            self.SESSION_LEAVE: [],
            self.CONNECTED: [],
            self.CLOSED: [],
        }

        # we just always loop over the transports when trying another
        # one
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
    def connect(self, reactor):
        """
        Starts connecting (possibly also re-connecting) and returns a
        Deferred that fires (with None) when we first connect.
        """

        while not self._shutting_down:
            try:
                transport_config = next(self._transport_gen)
                self.attempt_count += 1
                self.protocol = yield connect_to(
                    reactor,
                    transport_config,
                    self._create_session,
                    self._realm,
                    self._extra,
                )
                # note: we increment self._connect_count when the
                # ApplicationSession instance is created

                # "listen" for connectionLost
                orig = self.protocol.transport.connectionLost

                @wraps(self.protocol.transport.connectionLost)
                def wrapper(*args, **kw):
                    # callback with the Failure instance
                    rtn = orig(*args, **kw)
                    f = args[0]
                    print("LOST", args, kw)
                    if self.connect_count == 0:
                        self._fire_event(self.CLOSED, "unreachable")
                    else:
                        if isinstance(f.value, ConnectionDone):
                            self._fire_event(self.CLOSED, "closed")
                        else:
                            ### XXX javascrpt allows this to return
                            ### "false" to cancel reconnection
                            self._fire_event(self.CLOSED, "lost")
                    self.protocol = None

                    # XXX should probably base re-connection on above
                    # strings? or do it right in there too? (for
                    # consistency)

                    # initiate re-connection
                    print("connect count", self.connect_count)
                    if self.connect_count == 0:
                        if self._retry_on_unreachable and not self._shutting_down:
                            self.connect(reactor)
                    else:
                        # we've connected at least once before; keep trying
                        if not self._shutting_down:
                            self.connect(reactor)
                    return rtn
                self.protocol.transport.connectionLost = wrapper

                # we connected, so reset retry schedule if retry is
                # configured
                log.msg("Connected to '{}'".format(
                    json.dumps(transport_config)))
                self._fire_event(self.CONNECTED, self.protocol)
                if self._retry:
                    self._retry = self._retry_scheduler()
                return  # done with retrying; exit loop

            except Exception as e:
                log.err("Error connecting to '{}': {}".format(
                    json.dumps(transport_config), e))
                if self._retry:
                    try:
                        delay = next(self._retry)
                        print("retrying in {}s".format(delay))
                        yield sleep(delay)

                    except StopIteration:
                        print("Ran out of retry attempts")
                        raise RuntimeError("Failed to connect.")

                else:
                    self._fire_event(self.ERROR, e)
                    break
        print("leaving connect() loop")

    def _fire_event(self, evt, *args, **kw):
        """
        Internal helper. MUST NOT throw Exceptions
        """
        for cb in self._event_listeners[evt]:
            try:
                cb(*args, **kw)
            except Exception as e:
                print("While running callback {} for {}: {}".format(
                    cb, evt, e))

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


class ApplicationRunner(object):
    """
    Provides a high-level API that is (mostly) consistent across
    asyncio and Twisted code. It provides an easy way to configure
    transports and retry/re-connect options.

    If you want more control over the reactor and logging, see the
    :class:`Connection` class.

    If you need lower-level control than that, see :meth:`connect_to`
    which attempts a single connection to a single transport.
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

    def run(self, session_factory, start_reactor=True, retry=None):
        """
        Run an application component.

        :param session_factory: A callable that produces instances of
           :class:`autobahn.asyncio.wamp.ApplicationSession` when
           called with an instance of
           :class:`autobahn.wamp.types.ComponentConfig`. Usually this
           is simply your ``ApplicationSession`` subclass.
        :type make: callable

        :param start_reactor: if True (the default) this method starts
           the Twisted reactor and doesn't return until the reactor
           stops. If there are any problems starting the reactor or
           connect()-ing, we stop the reactor and raise the exception
           back to the caller.

        :param retry: dict configuring retry behaviour, or None/False

        :returns: None is returned, unless you specify
            ``start_reactor=False`` in which case you get a Deferred
            that will callback() when a connection is first
            established (WAMP session not yet joined at this point).
        """
        from twisted.internet import reactor
        txaio.use_twisted()
        txaio.config.loop = reactor

        # XXX FIXME should we really start logging automagically? or
        # not... or provide a "start_logging=True" kwarg?

        # XXX I guess the "experts" interface is:
        # Connection(..).connect() and then you can start logging however you want...?
        log.startLogging(sys.stdout)

        self.connection = Connection(
            session_factory,
            self.transports,
            self.realm,
            self.extra,
            retry
        )

        def on_error(e):
            if e is not None:
                print("Error:", e)
            if start_reactor:
                reactor.stop()
        self.connection.add_event(Connection.ERROR, on_error)

        # if the user didn't ask us to start the reactor, then they
        # get to deal with any connect errors themselves.
        if start_reactor:
            # if an error happens in the connect(), we save the underlying
            # exception so that after the event-loop exits we can re-raise
            # it to the caller.

            class ErrorCollector(object):
                exception = None

                def __call__(self, failure):
                    self.exception = failure.value
                    print(failure.getErrorMessage())
                    if reactor.running:
                        reactor.stop()
            connect_error = ErrorCollector()

            def startup():
                d = self.connection.connect(reactor)
                d.addErrback(connect_error)
            reactor.callWhenRunning(startup)

            # now enter the Twisted reactor loop
            reactor.run()

            # if we exited due to a connection error, raise that to the
            # caller
            if connect_error.exception:
                raise connect_error.exception

        else:
            # let the caller handle any errors
            d = self.connection.connect(reactor)
            # we return a Connection instance ("_" will be IProtocol)
            d.addCallback(lambda _: self.connection)
            return d


class _ApplicationSession(ApplicationSession):
    """
    WAMP application session class used internally with
    :class:`autobahn.twisted.app.Application`.
    """

    def __init__(self, config, app):
        """

        :param config: The component configuration.
        :type config: Instance of :class:`autobahn.wamp.types.ComponentConfig`
        :param app: The application this session is for.
        :type app: Instance of :class:`autobahn.twisted.wamp.Application`.
        """
        # noinspection PyArgumentList
        ApplicationSession.__init__(self, config)
        self.app = app

    @inlineCallbacks
    def onConnect(self):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onConnect`
        """
        yield self.app._fire_signal('onconnect')
        self.join(self.config.realm)

    @inlineCallbacks
    def onJoin(self, details):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onJoin`
        """
        for uri, proc in self.app._procs:
            yield self.register(proc, uri)

        for uri, handler in self.app._handlers:
            yield self.subscribe(handler, uri)

        yield self.app._fire_signal('onjoined')

    @inlineCallbacks
    def onLeave(self, details):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onLeave`
        """
        yield self.app._fire_signal('onleave')
        self.disconnect()

    @inlineCallbacks
    def onDisconnect(self):
        """
        Implements :func:`autobahn.wamp.interfaces.ISession.onDisconnect`
        """
        yield self.app._fire_signal('ondisconnect')


class Application(object):
    """
    A WAMP application. The application object provides a simple way of
    creating, debugging and running WAMP application components.
    """

    def __init__(self, prefix=None):
        """
        :param prefix: The application URI prefix to use for
           procedures and topics, e.g. ``"com.example.myapp"``.
        :type prefix: unicode
        """
        self._prefix = prefix

        #: procedures to be registered once the app session has joined
        #: the router/realm
        self._procs = []

        #: event handler to be subscribed once the app session has
        #: joined the router/realm
        self._handlers = []

        #: app lifecycle signal handlers
        self._signals = {}

        #: once an app session is connected, this will be that instance
        self.session = None

    def __call__(self, config):
        """
        Factory creating a WAMP application session for the application.

        :param config: Component configuration.
        :type config: Instance of :class:`autobahn.wamp.types.ComponentConfig`

        :returns: obj -- An object that derives of
           :class:`autobahn.twisted.wamp.ApplicationSession`
        """
        assert(self.session is None)
        self.session = _ApplicationSession(config, self)
        return self.session

    def run(self, url=u"ws://localhost:8080/ws", realm=u"realm1",
            debug=False, debug_wamp=False, debug_app=False,
            start_reactor=True):
        """
        Run the application.

        :param url: The URL of the WAMP router to connect to.
        :type url: unicode
        :param realm: The realm on the WAMP router to join.
        :type realm: unicode
        :param debug: Turn on low-level debugging.
        :type debug: bool
        :param debug_wamp: Turn on WAMP-level debugging.
        :type debug_wamp: bool
        :param debug_app: Turn on app-level debugging.
        :type debug_app: bool
        """
        runner = ApplicationRunner(url, realm,
                                   debug=debug, debug_wamp=debug_wamp, debug_app=debug_app)
        runner.run(self.__call__, start_reactor)

    def register(self, uri=None):
        """
        Decorator exposing a function as a remote callable procedure.

        The first argument of the decorator should be the URI of the procedure
        to register under.

        :Example:

        .. code-block:: python

           @app.register('com.myapp.add2')
           def add2(a, b):
              return a + b

        Above function can then be called remotely over WAMP using the URI `com.myapp.add2`
        the function was registered under.

        If no URI is given, the URI is constructed from the application URI prefix
        and the Python function name.

        :Example:

        .. code-block:: python

           app = Application('com.myapp')

           # implicit URI will be 'com.myapp.add2'
           @app.register()
           def add2(a, b):
              return a + b

        If the function `yields` (is a co-routine), the `@inlineCallbacks` decorator
        will be applied automatically to it. In that case, if you wish to return something,
        you should use `returnValue`:

        :Example:

        .. code-block:: python

           from twisted.internet.defer import returnValue

           @app.register('com.myapp.add2')
           def add2(a, b):
              res = yield stuff(a, b)
              returnValue(res)

        :param uri: The URI of the procedure to register under.
        :type uri: unicode
        """
        def decorator(func):
            if uri:
                _uri = uri
            else:
                assert(self._prefix is not None)
                _uri = "{0}.{1}".format(self._prefix, func.__name__)

            if inspect.isgeneratorfunction(func):
                func = inlineCallbacks(func)

            self._procs.append((_uri, func))
            return func
        return decorator

    def subscribe(self, uri=None):
        """
        Decorator attaching a function as an event handler.

        The first argument of the decorator should be the URI of the topic
        to subscribe to. If no URI is given, the URI is constructed from
        the application URI prefix and the Python function name.

        If the function yield, it will be assumed that it's an asynchronous
        process and inlineCallbacks will be applied to it.

        :Example:

        .. code-block:: python

           @app.subscribe('com.myapp.topic1')
           def onevent1(x, y):
              print("got event on topic1", x, y)

        :param uri: The URI of the topic to subscribe to.
        :type uri: unicode
        """
        def decorator(func):
            if uri:
                _uri = uri
            else:
                assert(self._prefix is not None)
                _uri = "{0}.{1}".format(self._prefix, func.__name__)

            if inspect.isgeneratorfunction(func):
                func = inlineCallbacks(func)

            self._handlers.append((_uri, func))
            return func
        return decorator

    def signal(self, name):
        """
        Decorator attaching a function as handler for application signals.

        Signals are local events triggered internally and exposed to the
        developer to be able to react to the application lifecycle.

        If the function yield, it will be assumed that it's an asynchronous
        coroutine and inlineCallbacks will be applied to it.

        Current signals :

           - `onjoined`: Triggered after the application session has joined the
              realm on the router and registered/subscribed all procedures
              and event handlers that were setup via decorators.
           - `onleave`: Triggered when the application session leaves the realm.

        .. code-block:: python

           @app.signal('onjoined')
           def _():
              # do after the app has join a realm

        :param name: The name of the signal to watch.
        :type name: unicode
        """
        def decorator(func):
            if inspect.isgeneratorfunction(func):
                func = inlineCallbacks(func)
            self._signals.setdefault(name, []).append(func)
            return func
        return decorator

    @inlineCallbacks
    def _fire_signal(self, name, *args, **kwargs):
        """
        Utility method to call all signal handlers for a given signal.

        :param name: The signal name.
        :type name: str
        """
        for handler in self._signals.get(name, []):
            try:
                # FIXME: what if the signal handler is not a coroutine?
                # Why run signal handlers synchronously?
                yield handler(*args, **kwargs)
            except Exception as e:
                # FIXME
                log.msg("Warning: exception in signal handler swallowed", e)


if service:
    # Don't define it if Twisted's service support isn't here

    class Service(service.MultiService):
        """
        A WAMP application as a twisted service.
        The application object provides a simple way of creating, debugging and running WAMP application
        components inside a traditional twisted application

        This manages application lifecycle of the wamp connection using startService and stopService
        Using services also allows to create integration tests that properly terminates their connections

        It can host a WAMP application component in a WAMP-over-WebSocket client
        connecting to a WAMP router.
        """
        factory = WampWebSocketClientFactory

        def __init__(self, url, realm, make, extra=None,
                     debug=False, debug_wamp=False, debug_app=False):
            """

            :param url: The WebSocket URL of the WAMP router to connect to (e.g. `ws://somehost.com:8090/somepath`)
            :type url: unicode
            :param realm: The WAMP realm to join the application session to.
            :type realm: unicode
            :param make: A factory that produces instances of :class:`autobahn.asyncio.wamp.ApplicationSession`
               when called with an instance of :class:`autobahn.wamp.types.ComponentConfig`.
            :type make: callable
            :param extra: Optional extra configuration to forward to the application component.
            :type extra: dict
            :param debug: Turn on low-level debugging.
            :type debug: bool
            :param debug_wamp: Turn on WAMP-level debugging.
            :type debug_wamp: bool
            :param debug_app: Turn on app-level debugging.
            :type debug_app: bool

            You can replace the attribute factory in order to change connectionLost or connectionFailed behaviour.
            The factory attribute must return a WampWebSocketClientFactory object
            """
            self.url = url
            self.realm = realm
            self.extra = extra or dict()
            self.debug = debug
            self.debug_wamp = debug_wamp
            self.debug_app = debug_app
            self.make = make
            service.MultiService.__init__(self)
            self.setupService()

        def setupService(self):
            """
            Setup the application component.
            """
            isSecure, host, port, resource, path, params = parseWsUrl(self.url)

            # factory for use ApplicationSession
            def create():
                cfg = ComponentConfig(self.realm, self.extra)
                session = self.make(cfg)
                session.debug_app = self.debug_app
                return session

            # create a WAMP-over-WebSocket transport client factory
            transport_factory = self.factory(create, url=self.url,
                                             debug=self.debug, debug_wamp=self.debug_wamp)

            # setup the client from a Twisted endpoint

            if isSecure:
                from twisted.application.internet import SSLClient
                clientClass = SSLClient
            else:
                from twisted.application.internet import TCPClient
                clientClass = TCPClient

            client = clientClass(host, port, transport_factory)
            client.setServiceParent(self)
