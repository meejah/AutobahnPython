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

import six
import inspect

import txaio
txaio.use_twisted()  # noqa

from twisted.internet.defer import inlineCallbacks, maybeDeferred

from autobahn.websocket.util import parse_url as parse_ws_url
from autobahn.rawsocket.util import parse_url as parse_rs_url

from autobahn.twisted.websocket import WampWebSocketClientFactory
from autobahn.twisted.rawsocket import WampRawSocketClientFactory

from autobahn.websocket.compress import PerMessageDeflateOffer, \
    PerMessageDeflateResponse, PerMessageDeflateResponseAccept

from autobahn.wamp import protocol
from autobahn.wamp.types import ComponentConfig

__all__ = [
    'ApplicationSession',
    'ApplicationSessionFactory',
    'ApplicationRunner',
    'Application',
    'Service',

    # new API
    'Session'
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


class ApplicationSessionFactory(protocol.ApplicationSessionFactory):
    """
    WAMP application session factory for Twisted-based applications.
    """

    session = ApplicationSession
    """
    The application session class this application session factory will use. Defaults to :class:`autobahn.twisted.wamp.ApplicationSession`.
    """


class ApplicationRunner(object):
    """
    This class is a convenience tool mainly for development and quick hosting
    of WAMP application components.

    It can host a WAMP application component in a WAMP-over-WebSocket client
    connecting to a WAMP router.
    """

    log = txaio.make_logger()

    def __init__(self, url, realm, extra=None, serializers=None, ssl=None, proxy=None, headers=None):
        """

        :param url: The WebSocket URL of the WAMP router to connect to (e.g. `ws://somehost.com:8090/somepath`)
        :type url: unicode

        :param realm: The WAMP realm to join the application session to.
        :type realm: unicode

        :param extra: Optional extra configuration to forward to the application component.
        :type extra: dict

        :param serializers: A list of WAMP serializers to use (or None for default serializers).
           Serializers must implement :class:`autobahn.wamp.interfaces.ISerializer`.
        :type serializers: list

        :param ssl: (Optional). If specified this should be an
            instance suitable to pass as ``sslContextFactory`` to
            :class:`twisted.internet.endpoints.SSL4ClientEndpoint`` such
            as :class:`twisted.internet.ssl.CertificateOptions`. Leaving
            it as ``None`` will use the result of calling Twisted's
            :meth:`twisted.internet.ssl.platformTrust` which tries to use
            your distribution's CA certificates.
        :type ssl: :class:`twisted.internet.ssl.CertificateOptions`

        :param proxy: Explicit proxy server to use; a dict with ``host`` and ``port`` keys
        :type proxy: dict or None
        """
        assert(type(url) == six.text_type)
        assert(realm is None or type(realm) == six.text_type)
        assert(extra is None or type(extra) == dict)
        assert(proxy is None or type(proxy) == dict)
        self.url = url
        self.realm = realm
        self.extra = extra or dict()
        self.serializers = serializers
        self.ssl = ssl
        self.proxy = proxy
        self.headers = headers

    def run(self, make, start_reactor=True, auto_reconnect=False, log_level='info'):
        """
        Run the application component.

        :param make: A factory that produces instances of :class:`autobahn.asyncio.wamp.ApplicationSession`
           when called with an instance of :class:`autobahn.wamp.types.ComponentConfig`.
        :type make: callable

        :param start_reactor: if True (the default) this method starts
           the Twisted reactor and doesn't return until the reactor
           stops. If there are any problems starting the reactor or
           connect()-ing, we stop the reactor and raise the exception
           back to the caller.

        :returns: None is returned, unless you specify
            ``start_reactor=False`` in which case the Deferred that
            connect() returns is returned; this will callback() with
            an IProtocol instance, which will actually be an instance
            of :class:`WampWebSocketClientProtocol`
        """
        if start_reactor:
            # only select framework, set loop and start logging when we are asked
            # start the reactor - otherwise we are running in a program that likely
            # already tool care of all this.
            from twisted.internet import reactor
            txaio.use_twisted()
            txaio.config.loop = reactor
            txaio.start_logging(level=log_level)

        if callable(make):
            # factory for use ApplicationSession
            def create():
                cfg = ComponentConfig(self.realm, self.extra)
                try:
                    session = make(cfg)
                except Exception as e:
                    if start_reactor:
                        # the app component could not be created .. fatal
                        self.log.error("{err}", err=e)
                        reactor.stop()
                    else:
                        # if we didn't start the reactor, it's up to the
                        # caller to deal with errors
                        raise
                else:
                    return session
        else:
            create = make

        if self.url.startswith(u'rs'):
            # try to parse RawSocket URL ..
            isSecure, host, port = parse_rs_url(self.url)

            # create a WAMP-over-RawSocket transport client factory
            transport_factory = WampRawSocketClientFactory(create)

        else:
            # try to parse WebSocket URL ..
            isSecure, host, port, resource, path, params = parse_ws_url(self.url)

            # create a WAMP-over-WebSocket transport client factory
            transport_factory = WampWebSocketClientFactory(create, url=self.url, serializers=self.serializers, proxy=self.proxy, headers=self.headers)

            # client WebSocket settings - similar to:
            # - http://crossbar.io/docs/WebSocket-Compression/#production-settings
            # - http://crossbar.io/docs/WebSocket-Options/#production-settings

            # The permessage-deflate extensions offered to the server ..
            offers = [PerMessageDeflateOffer()]

            # Function to accept permessage_delate responses from the server ..
            def accept(response):
                if isinstance(response, PerMessageDeflateResponse):
                    return PerMessageDeflateResponseAccept(response)

            # set WebSocket options for all client connections
            transport_factory.setProtocolOptions(maxFramePayloadSize=1048576,
                                                 maxMessagePayloadSize=1048576,
                                                 autoFragmentSize=65536,
                                                 failByDrop=False,
                                                 openHandshakeTimeout=2.5,
                                                 closeHandshakeTimeout=1.,
                                                 tcpNoDelay=True,
                                                 autoPingInterval=10.,
                                                 autoPingTimeout=5.,
                                                 autoPingSize=4,
                                                 perMessageCompressionOffers=offers,
                                                 perMessageCompressionAccept=accept)

        # supress pointless log noise
        transport_factory.noisy = False

        # if user passed ssl= but isn't using isSecure, we'll never
        # use the ssl argument which makes no sense.
        context_factory = None
        if self.ssl is not None:
            if not isSecure:
                raise RuntimeError(
                    'ssl= argument value passed to %s conflicts with the "ws:" '
                    'prefix of the url argument. Did you mean to use "wss:"?' %
                    self.__class__.__name__)
            context_factory = self.ssl
        elif isSecure:
            from twisted.internet.ssl import optionsForClientTLS
            context_factory = optionsForClientTLS(host)

        from twisted.internet import reactor
        if self.proxy is not None:
            from twisted.internet.endpoints import TCP4ClientEndpoint
            client = TCP4ClientEndpoint(reactor, self.proxy['host'], self.proxy['port'])
            transport_factory.contextFactory = context_factory
        elif isSecure:
            from twisted.internet.endpoints import SSL4ClientEndpoint
            assert context_factory is not None
            client = SSL4ClientEndpoint(reactor, host, port, context_factory)
        else:
            from twisted.internet.endpoints import TCP4ClientEndpoint
            client = TCP4ClientEndpoint(reactor, host, port)

        # as the reactor shuts down, we wish to wait until we've sent
        # out our "Goodbye" message; leave() returns a Deferred that
        # fires when the transport gets to STATE_CLOSED
        def cleanup(proto):
            if hasattr(proto, '_session') and proto._session is not None:
                if proto._session.is_attached():
                    return proto._session.leave()
                elif proto._session.is_connected():
                    return proto._session.disconnect()

        # when our proto was created and connected, make sure it's cleaned
        # up properly later on when the reactor shuts down for whatever reason
        def init_proto(proto):
            reactor.addSystemEventTrigger('before', 'shutdown', cleanup, proto)
            return proto

        use_service = False
        if auto_reconnect:
            try:
                # since Twisted 16.1.0
                from twisted.application.internet import ClientService
                use_service = True
            except ImportError:
                use_service = False

        if use_service:
            self.log.debug('using t.a.i.ClientService')
            # this is automatically reconnecting
            service = ClientService(client, transport_factory)
            service.startService()
            d = service.whenConnected()
        else:
            # this is only connecting once!
            self.log.debug('using t.i.e.connect()')
            d = client.connect(transport_factory)

        # if we connect successfully, the arg is a WampWebSocketClientProtocol
        d.addCallback(init_proto)

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
                    reactor.stop()
            connect_error = ErrorCollector()
            d.addErrback(connect_error)

            # now enter the Twisted reactor loop
            reactor.run()

            # if we exited due to a connection error, raise that to the
            # caller
            if connect_error.exception:
                raise connect_error.exception

        else:
            # let the caller handle any errors
            return d


class _ApplicationSession(ApplicationSession):
    """
    WAMP application session class used internally with :class:`autobahn.twisted.app.Application`.
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

    log = txaio.make_logger()

    def __init__(self, prefix=None):
        """

        :param prefix: The application URI prefix to use for procedures and topics,
           e.g. ``"com.example.myapp"``.
        :type prefix: unicode
        """
        self._prefix = prefix

        # procedures to be registered once the app session has joined the router/realm
        self._procs = []

        # event handler to be subscribed once the app session has joined the router/realm
        self._handlers = []

        # app lifecycle signal handlers
        self._signals = {}

        # once an app session is connected, this will be here
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

    def run(self, url=u"ws://localhost:8080/ws", realm=u"realm1", start_reactor=True):
        """
        Run the application.

        :param url: The URL of the WAMP router to connect to.
        :type url: unicode
        :param realm: The realm on the WAMP router to join.
        :type realm: unicode
        """
        runner = ApplicationRunner(url, realm)
        return runner.run(self.__call__, start_reactor)

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
                self.log.info("Warning: exception in signal handler swallowed: {err}", err=e)


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

        def __init__(self, url, realm, make, extra=None, context_factory=None):
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

            :param context_factory: optional, only for secure connections. Passed as contextFactory to
                the ``listenSSL()`` call; see https://twistedmatrix.com/documents/current/api/twisted.internet.interfaces.IReactorSSL.connectSSL.html
            :type context_factory: twisted.internet.ssl.ClientContextFactory or None

            You can replace the attribute factory in order to change connectionLost or connectionFailed behaviour.
            The factory attribute must return a WampWebSocketClientFactory object
            """
            self.url = url
            self.realm = realm
            self.extra = extra or dict()
            self.make = make
            self.context_factory = context_factory
            service.MultiService.__init__(self)
            self.setupService()

        def setupService(self):
            """
            Setup the application component.
            """
            is_secure, host, port, resource, path, params = parse_ws_url(self.url)

            # factory for use ApplicationSession
            def create():
                cfg = ComponentConfig(self.realm, self.extra)
                session = self.make(cfg)
                return session

            # create a WAMP-over-WebSocket transport client factory
            transport_factory = self.factory(create, url=self.url)

            # setup the client from a Twisted endpoint

            if is_secure:
                from twisted.application.internet import SSLClient
                ctx = self.context_factory
                if ctx is None:
                    from twisted.internet.ssl import optionsForClientTLS
                    ctx = optionsForClientTLS(host)
                client = SSLClient(host, port, transport_factory, contextFactory=ctx)
            else:
                if self.context_factory is not None:
                    raise Exception("context_factory specified on non-secure URI")
                from twisted.application.internet import TCPClient
                client = TCPClient(host, port, transport_factory)

            client.setServiceParent(self)


from autobahn.wamp import cryptosign
from zope.interface import implementer, Interface, Attribute


# XXX playing with a nicer authentication API than "override
# onConnect() and you must do everything by hand"...

class IWampAuthenticationMethod(Interface):
    """
    Defines the interface which a WAMP authentication must
    provide. Typically, you should be able to "just use" one of the
    built-in implementers of this interface.

    If you wish to implement your own authentication, you can either
    provide an object that implements this API (preferred) **or**
    subclass ApplicationSession and override onConnect.

    There are built-in objects that implement this interface for
    existing WAMP authentication methods.
    """

    wamp_method_name = Attribute(
        "The unicode string that is the name by which this authentication"
        " method is known to WAMP (e.g. u'cryptosign', or u'wampcra')"
    )

    def get_authextra(self):
        """
        Return a dict() containing any additional information this
        authenticator needs to pass along with the join() call.
        """

    def on_challenge(self, session, challenge):
        """
        Called with the challenge object when a Session gets onChallenge
        for this authentication method. May be async. Must return a
        signature (i.e. answer to the challenge).
        """


@implementer(IWampAuthenticationMethod)
class AnonymousAuthenticator(object):
    """
    Implments WAMP-Anonymous for use as a Session authenticator
    """

    wamp_method_name = u"anonymous"

    @classmethod
    def from_config(cls, config):
        assert config.get(u'name', None) == cls.wamp_method_name
        return cls()

    def get_authextra(self):
        r = dict()
        return r

    def on_challenge(self, session, challenge):
        raise RuntimeError("Received challenge for anonymous authentication")


@implementer(IWampAuthenticationMethod)
class CryptoSignAuthenticator(object):
    """
    Implments WAMP-CryptoSign for use as a Session authenticator
    """

    wamp_method_name = u'cryptosign'

    @classmethod
    def from_config(cls, config):
        assert config.get(u'name', None) == cls.wamp_method_name
        return cls(
            key_data=config.get('key_data', None),
            key_fname=config.get('key_fname', None),
        )

    def __init__(self, key_data=None, key_fname=None):
        if key_data is not None and key_fname is not None:
            raise ValueError(
                "Cannot pass both 'key_data' and 'key_fname'"
            )
        if key_data is not None:
            self._key = cryptosign.SigningKey.from_data(key_data)
        elif key_fname is not None:
            self._key = cryptosign.SigningKey.from_raw_key(key_fname)
        else:
            raise ValueError(
                "cryptosign authenticator requires one of 'key_data' "
                "or 'key_fname'"
            )

    def get_authextra(self):
        return {
            u'pubkey': self._key.public_key(),
            u'channel_binding': u'tls-unique',
        }

    def on_challenge(self, session, challenge):
        return self._key.sign_challenge(session, challenge)


@implementer(IWampAuthenticationMethod)
class ChallengeResponseAuthenticator(object):
    """
    Implments WAMP-CRA for use as a Session authenticator
    """
    wamp_method_name = u'wampcra'

    @classmethod
    def from_config(cls, config):
        assert config.get(u'name', None) == cls.wamp_method_name
        if u'secret' not in config:
            raise ValueError("wampcra config requires 'secret' key")
        return ChallengeResponseAuthenticator(config.get(u'secret'))

    def __init__(self, secret):
        self._secret = secret

    def get_authextra(self):
        return None

    def on_challenge(self, session, challenge):
        if u'salt' in challenge.extra:
           # salted secret
           key = auth.derive_key(
               self._secret,
               challenge.extra['salt'],
               challenge.extra['iterations'],
               challenge.extra['keylen'],
           )
        else:
           # plain, unsalted secret
           key = self._secret

        # compute signature for challenge, using the key
        return auth.compute_wcs(key, challenge.extra['challenge'])


def authenticator_from_config(config):
    """
    Given a dict from the 'methods' list of a wamp authentication
    config, this returns an instance implementing IWampAuthenticationMethod
    (or exception).
    """
    for key in [u'name']:
        if key not in config:
            raise ValueError("method config requires '{}'".format(key))
    name = config.get(u'name')
    name_to_authenticator = {
        u'anonymous': AnonymousAuthenticator,
        u'wampcra': ChallengeResponseAuthenticator,
        u'cryptosign': CryptoSignAuthenticator,
    }
    try:
        return name_to_authenticator[name].from_config(config)
    except KeyError:
        raise ValueError(
            "Unknown authentication method '{}'".format(name)
        )


class WampAuthenticator(object):
    """
    Represents configuration of authentication. This includes the
    target realm, authid, any extra data. The actual authentication
    methods are supported by objects implementing IWampAuthenticationMethod
    """

    @staticmethod
    def from_config(config, realm=None):
        """
        :param realm str: a realm to use if one isn't provided in the config

        Given a config dict, this returns a fresh WampAuthenticator
        instance. Config is:

        - realm: (required) the realm to join
        - authid: (optional) passed along as authid
        - authextra: (optional) passed along as authextra
        - methods: (required) list of acceptable methods to use, and their options

        Each entry in the `methods` list should itself be a dict, with
        the following keys:
        - name: the name of a valid WAMP authentication method (e.g. "cryptosign")
        - key_data: (cryptosign) hex-encoded private key data
        - key_fname: (cryptosign) filename containing private key data
        - secret: (wampcra) the WAMP-CRA secret
        """
        if not isinstance(config, dict):
            raise ValueError("config must be a dict")

        for key in config.keys():
            # note: authextra provided by individual authenticator
            if key not in [u'realm', u'methods', u'authid']:
                raise ValueError("Unknown config key '{}'".format(key))

        for key in [u'methods']:
            if key not in config:
                raise ValueError("config must contain key '{}'".format(key))

        realm = config.get(u'realm', realm)
        if realm is None:
            raise ValueError("Session didn't provide 'realm' and neither did the config")
        auth = WampAuthenticator(
            realm,
            authid=config.get(u'authid', None),
        )
        for method_cfg in config['methods']:
            if IWampAuthenticationMethod.providedBy(method_cfg):
                auth.add_method(method_cfg)
            else:
                auth.add_method(authenticator_from_config(method_cfg))
        return auth

    def __init__(self, realm, authid=None):
        if not isinstance(realm, six.text_type):
            raise ValueError("realm must be a {} (got {})".format(
                six.text_type.__name__,
                realm.__class__.__name__,
            ))
        self._realm = realm
        self._authid = authid
        # maps method_name -> IWampAuthentication instance
        self._authenticators = dict()

    def add_method(self, authenticator):
        """
        :param authenticator: an object implementing IWampAuthenticationMethod
        """
        if not IWampAuthenticationMethod.providedBy(authenticator):
            raise ValueError(
                "authenticator must provide IWampAuthentication"
            )
        method = authenticator.wamp_method_name
        # XXX check method isinstance unicode?
        if method in self._authenticators:
            raise ValueError(
                "Already have an authenticator for '{}'".format(method)
            )
        self._authenticators[method] = authenticator

    def remove_method(self, name):
        """
        Remove a previously added authentication method.

        :param name str: the name of the authentication method
        (e.g. "anonymous", "cryptosign", ..)

        """
        try:
            del self._authenticators[name]
        except KeyError:
            raise ValueError(
                "Can't find authentication method '{}'".format(name)
            )

    def join_session(self, session):
        """
        hook called by Session to allow us to do the .join() call on it
        """
        authextra = dict()
        for name, method in self._authenticators.items():
            extra = method.get_authextra()
            for k, v in extra.items():
                if k in authextra and authextra[k] != v:
                    raise RuntimeError(
                        "Conflicting authextra information; two different "
                        "authenticators want to set '{}'. One wants '{}' and "
                        "the other wants '{}'.".format(k, v, authextra[k])
                    )
                authextra[k] = v

        return session.join(
            self._realm,
            authmethods=list(self._authenticators.keys()),
            authid=self._authid,  # can be None
            authextra=authextra,
        )

    def on_challenge(self, session, challenge):
        """
        hook called by Session when a challenge is received; forwards the
        challenge to the correct authenticator
        """
        try:
            return self._authenticators[challenge.method].on_challenge(session, challenge)
        except KeyError:
            # XXX should be a WAMP protocol error?
            raise RuntimeError(
                "Got on_challenge for unknown authenticator '{}'".format(challenge.method)
            )


# new API
class Session(ApplicationSession):
    # shim that lets us present pep8 API for user-classes to override,
    # but also backwards-compatible for existing code using
    # ApplicationSession "directly".

    # XXX note to self: if we release this as "the" API, then we can
    # change all internal Autobahn calls to .on_join() etc, and make
    # ApplicationSession a subclass of Session -- and it can then be
    # separate deprecated and removed, ultimately, if desired.

    def onJoin(self, details):
        return self.on_join(details)

    #: either None or a WampAuthenticator instance
    _authenticator = None

    #: either None or a dict containing our authentication config
    #: (updated from set_auth_config)
    _authentication_config = None

    def configure_authentication(self):
        """
        This can be overridden as described in the interface (and can be
        async).

        This default method returns the last config set by
        `set_auth_config`, or return a new anonymous authentication
        config if set_auth_config was never called.

        """
        if self._authentication_config is None:
            self._authentication_config = {
                "realm": self.config.realm,
                "methods": [
                    {
                        "name": "anonymous",
                    }
                ]
            }
        return self._authentication_config

    def set_auth_config(self, config):
        """
        :param dict config: Contains a config valid for
        :meth:`autobahn.wamp.auth.WampAuthenticator.from_config`
        """
        self._authentication_config = dict()
        self._authentication_config.update(config)

    def onChallenge(self, challenge):
        """
        Do not override; not part of the public API. See
        :meth:`autobahn.twisted.wamp.Session.set_authenticator`
        """
        if self._authenticator is not None:
            return self._authenticator.on_challenge(self, challenge)
        return None

    @inlineCallbacks
    def onConnect(self):
        """
        Do not override; not part of the public API.
        """
        cfg = yield maybeDeferred(self.configure_authentication)
        self._authenticator = None
        if cfg is not None:
            if isinstance(cfg, WampAuthenticator):
                self._authenticator = cfg
            elif isinstance(cfg, dict):
                self._authenticator = WampAuthenticator.from_config(cfg)
            else:
                raise ValueError(
                    "configure_authentication() must return a WampAuthenticator"
                    " or dict or None"
                )
            yield self._authenticator.join_session(self)

        yield maybeDeferred(self.on_connect)
        return

    def onLeave(self, details):
        return self.on_leave(details)

    def onDisconnect(self):
        return self.on_disconnect()

    # this is the public API that you can override if need-be:

    def on_join(self, details):
        pass

    def on_leave(self, details):
        self.disconnect()

    def on_connect(self):
        pass

    def on_disconnect(self):
        pass
