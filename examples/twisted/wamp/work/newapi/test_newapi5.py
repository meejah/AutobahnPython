from twisted.internet.task import react
from twisted.internet.defer import inlineCallbacks as coroutine
from autobahn.twisted.component import Component


# this one no longer works at all


@coroutine
def main(reactor, component):

    transport = yield component.connect()
    session = yield transport.join(u'realm1')
    result = yield session.call(u'com.example.add2', 2, 3)
    yield session.leave()
    yield transport.disconnect()
    yield component.close()


if __name__ == '__main__':
    component = Component(realm=u'crossbardemo')
    component.on('start', main)

    react(component.start)
