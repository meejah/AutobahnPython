from __future__ import print_function

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

#    def onClose(self, *args, **kw):
#        raise RuntimeError("FOOOOO")

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

    retry = dict(
        initial_retry_delay=1,
        retry_growth_rate=2,
        max_retries=2,  # change to 1 for an error
        retry_on_unreachable=True,
    )

    if False: # retry
        connection = yield runner.run(ClientSession, start_reactor=False, retry=retry)
        runner = ApplicationRunner([bad_transport, bad_transport, rawsocket_unix_transport],#, bad_transport, bad_transport],
                                   u"realm1")
    else:
        runner = ApplicationRunner([rawsocket_unix_transport], u"realm1")
        #runner = ApplicationRunner([bad_transport], u"realm1")
        connection = yield runner.run(ClientSession, start_reactor=False)
    print("Connection!", connection)
    connection.add_event(Connection.CREATE_SESSION, lambda s: print("new session:", s))
    connection.add_event(Connection.SESSION_LEAVE, lambda s: print("session gone:", s))
    connection.add_event(Connection.CONNECTED, lambda p: print("protocol connected:", p))
    connection.add_event(Connection.ERROR, lambda e: print("connection error:", e))

    def shutdown(reason):
        print("shutdown", reason)
        reactor.stop()
    connection.add_event(Connection.CLOSED, shutdown)

    while True:
        yield sleep(1)
        print("connection:", connection)
    print("exiting main")

react(main)
print("exiting.")
