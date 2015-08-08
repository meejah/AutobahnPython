from __future__ import print_function

import time
import random
from functools import partial

from twisted.internet.endpoints import UNIXClientEndpoint
from twisted.internet.defer import inlineCallbacks, DeferredList, Deferred
from twisted.internet.task import react

from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner, Connection, connect_to
from autobahn.twisted.util import sleep
from autobahn.wamp.types import ComponentConfig


class ClientSession(ApplicationSession):
    joins = 2

    @inlineCallbacks
    def onJoin(self, details):
        print("joined:", details)
        self.joins = self.joins - 1
        sub = yield self.subscribe(self.subscription, "test.sub")
        print("subscribed:", sub)
        print("leaving in 6 seconds")
        yield sleep(6)
        # if you disconnect() then the reconnect logic still keeps
        # trying; if you leave() then it stops trying
        if False:
            print("disconnect()-ing")
            self.disconnect()
        else:
            print("leave()-ing")
            self.leave()

    def onLeave(self, details):
        print("onLeave:", details)
        from twisted.internet import reactor
        if self.joins > 0:
            print("re-joining in 2 seconds")
            reactor.callLater(2, self.join, self.config.realm)
        else:
            print("disconnecting in 3 seconds")
            reactor.callLater(3, self.disconnect)

    def onDisconnect(self):
        print("onDisconnect")

    def subscription(self, *args, **kw):
        print("sub:", args, kw)

    def __repr__(self):
        return '<ClientSession id={}>'.format(self._session_id)



bad_transport = {
    "type": "rawsocket",
    "endpoint": {
        "type": "unix",
        "path": "/tmp/cb-raw-foo",
    }
}

rawsocket_unix_transport = {
    "type": "rawsocket",
    "endpoint": {
        "type": "unix",
        "path": "/tmp/cb-raw",
    }
}

websocket_tcp_transport = {
    "type": "websocket",
    "url": "ws://localhost:8080/ws",
    "endpoint": {
        "type": "tcp",
        "host": "127.0.0.1",
        "port": 8080,
    }
}


@inlineCallbacks
def main(reactor):
    # we set up a transport that will definitely fail to demonstrate
    # re-connection as well. note that "transports" can be an iterable

    native_object_transport = {
        "type": "websocket",
        "url": "ws://localhost:8080/ws",
        "endpoint": UNIXClientEndpoint(reactor, '/tmp/cb-web')
    }

    transports = [
#        bad_transport,
        native_object_transport,
#        rawsocket_unix_transport,
#        websocket_tcp_transport,
#        {"just": "completely bogus"}
    ]

    def random_transports():
        while True:
            t = random.choice(transports)
            print("Returning transport: {}".format(t))
            yield t

    if False:
        # use generator/iterable as infinite transport list
        runner = ApplicationRunner(random_transports(), u"realm1")

        # single, good unix transport
        #runner = ApplicationRunner([rawsocket_unix_transport], u"realm1")

        # single, good tcp+websocket transport
        #runner = ApplicationRunner([websocket_tcp_transport], u"realm1")

        # single, bad transport (will never succeed)
        #runner = ApplicationRunner([bad_transport], u"realm1")

        # "advanced" usage, passing "start_reactor=False" so we get access to the connection object
        connection = yield runner.run(ClientSession, start_reactor=False)
        d = Deferred()

    elif True:
        # ...OR should just eliminate ^ start_reactor= and "make" you use
        # the Connection API directly if you want a Connection instance? like this:
        session = ClientSession(ComponentConfig(u"realm1", extra=None))

        def got_event(name, *args, **kw):
            print("got_event '{}' at '{}': {} {}".format(name, time.time(), args, kw))

        if False:
            for e in session.on._valid_events:
                session.on(e, partial(got_event, e))
        else:
            # multiple ways to subscribe...? or decide on one?
            session.on('join', partial(got_event, 'join'))
            session.on('leave', partial(got_event, 'leave'))
            session.on.ready(partial(got_event, 'ready'))
            session.on.connect(partial(got_event, 'connect'))
            session.on.disconnect(partial(got_event, 'disconnect'))
            session.on.disconnect.add(partial(got_event, 'disconnect'))

        connection = Connection(session, random_transports())
        print("about to open")
        d = connection.open(reactor)

    else:
        # lowest-level API, connecting a single transport, yielding an IProtocol
        # XXX consider making this one private for now? i.e. "_connect_to"
        connection = None
        proto = yield connect_to(reactor, rawsocket_unix_transport, ClientSession, u"realm1", None)
        print("Protocol {}".format(proto))
        d = sleep(10)
        print("done.")

    print("waiting for the all-done thing")
    x = yield d
    print("exiting main")


if False:
    # "normal" usage
    transports = [
        rawsocket_unix_transport,
        websocket_tcp_transport,
    ]

    #transports = [dict(url="ws://localhost:8080/ws")]

    runner = ApplicationRunner(transports, u"realm1")
    runner.run(ClientSession)
    print("exiting.")

else:
    # "Twisted native" and other "lower-level" usage
    react(main)
    print("exiting.")
