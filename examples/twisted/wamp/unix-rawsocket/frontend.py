from __future__ import print_function

import random

from twisted.internet.defer import inlineCallbacks, DeferredList, Deferred
from twisted.internet.task import react

from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner, Connection
from autobahn.twisted.util import sleep


class ClientSession(ApplicationSession):
    @inlineCallbacks
    def onJoin(self, details):
        print("Joined", details)
        sub = yield self.subscribe(self.subscription, "test.sub")
        print("subscribed", sub)
        print("disconnecting in 6 seconds")
        yield sleep(6)
        # if you disconnect() then the reconnect logic still keeps
        # trying; if you leave() then it stops trying
        if False:
            print("disconnect()-ing")
            self.disconnect()
        else:
            print("leave()-ing")
            self.leave()

    def subscription(self, *args, **kw):
        print("sub:", args, kw)


@inlineCallbacks
def main(reactor):
    # we set up a transport that will definitely fail to demonstrate
    # re-connection as well. note that "transports" can be an iterable

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
        "url": "ws://127.0.0.1/ws",
        "endpoint": {
            "type": "tcp",
            "host": "127.0.0.1",
            "port": 8081,
        }
    }

    transports = [bad_transport, rawsocket_unix_transport, websocket_tcp_transport, {"just": "completely bogus"}]
    def random_transports():
        while True:
            t = random.choice(transports)
            # print("Returning transport:", t)
            yield t

    # single, good unix transport
    #runner = ApplicationRunner([rawsocket_unix_transport], u"realm1")

    # single, good tcp+websocket transport
    #runner = ApplicationRunner([websocket_tcp_transport], u"realm1")

    # single, bad transport (will never succeed)
    #runner = ApplicationRunner([bad_transport], u"realm1")

    if False:
        # use generator/iterable as infinite transport list
        runner = ApplicationRunner(random_transports(), u"realm1")

        # "advanced" usage, passing "start_reactor=False" so we get access to the connection object
        connection = yield runner.run(ClientSession, start_reactor=False)
    else:
        # ...OR should just "make" you use the Connection API directly?
        connection = Connection(ClientSession, random_transports(), u"realm1", None)
        yield connection.connect(reactor)

    print("Connection!", connection)
    connection.add_event(Connection.CREATE_SESSION, lambda s: print("new session:", s))
    connection.add_event(Connection.SESSION_LEAVE, lambda s: print("session gone:", s))
    connection.add_event(Connection.CONNECTED, lambda p: print("protocol connected:", p))
    connection.add_event(Connection.ERROR, lambda e: print("connection error:", e))

    def shutdown(reason):
        print("shutdown because '{}'".format(reason))
        #reactor.stop()
    connection.add_event(Connection.CLOSED, shutdown)

    while True:
        yield sleep(1)
        print("connection:", connection)
        if connection.session:
            connection.session.publish('foo')
    print("exiting main")

react(main)
print("exiting.")
