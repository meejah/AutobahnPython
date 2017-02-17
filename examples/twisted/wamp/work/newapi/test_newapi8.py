from twisted.internet.task import react, deferLater
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks as coroutine
from autobahn.twisted.component import Component, run
from autobahn.twisted.wamp import Session

# A single session joins a first realm, leaves and joins another realm
# all over the same, still running transport

# (now, we can do this in an on_join:)
# @component.on_join
# @inlineCallback
# def _(session, details):
#     yield session.leave()
#     yield session.join(u'another_realm')
# okay, so the default implementation of ApplicationSession overrides
# leave() to do a disconnect .. so we have to override that.

class _NoDisconnect(Session):
    def onLeave(self, details):
        pass


component = Component(realm=u'crossbardemo')
component.session_factory = _NoDisconnect


@component.on_join
@coroutine
def on_join(session, details):
    print("joined: {}".format(details))
    if details.realm != u'another_realm':
        print("switching realms")
        session.leave()
        print("Left; waiting 2 seconds")
        yield deferLater(reactor, 2, lambda: None)
        print("joining 'another_realm'")
        yield session.join(u'another_realm')
    else:
        print("waiting 5 seconds")
        for x in range(5):
            print("{}...".format(x + 1))
            yield deferLater(reactor, 1, lambda: None)
        print("leaving")
        session.leave()
        print("Disconnectin in 1 second")
        yield deferLater(reactor, 1, lambda: None)
        print("disconnecting")
        yield session.disconnect()



if __name__ == '__main__':
    run(component, 'info')
