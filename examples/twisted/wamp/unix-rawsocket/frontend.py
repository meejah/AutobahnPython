from __future__ import print_function

import random

from twisted.internet.endpoints import UNIXClientEndpoint
from twisted.internet.defer import inlineCallbacks, DeferredList, Deferred
from twisted.internet.task import react

from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner, Connection, connect_to
from autobahn.twisted.util import sleep


class ClientSession(ApplicationSession):
    @inlineCallbacks
    def onJoin(self, details):
        print("Joined", details)
        sub = yield self.subscribe(self.subscription, "test.sub")
        print("subscribed", sub)
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
        print("onleave", details)
        print("disconnecting in 3 seconds")
        from twisted.internet import reactor
        reactor.callLater(3, self.disconnect)

    def onDisconnect(self):
        print("DISCONECT")

    def subscription(self, *args, **kw):
        print("sub:", args, kw)



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
        connection = Connection(ClientSession, random_transports(), u"realm1", extra=None)

        def blam(*args, **kw):
            print("ZZXXCC", args, kw)
            sys.stdout.write('{} {}\n'.format(args, kw))
        connection.on('join', blam)
        connection.on('leave', blam)
        connection.on.connect(blam)
        connection.on.disconnect(blam)
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
