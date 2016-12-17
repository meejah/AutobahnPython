from twisted.internet.task import react
from twisted.internet.defer import inlineCallbacks as coroutine
from autobahn.twisted.component import Component


# this one no longer works; main takes reactor, session


@coroutine
def main(transport):
    print("ohai!", transport)
    session = yield transport.join(u'myrealm1')
    result = yield session.call(u'com.myapp.add2', 2, 3)
    print("Result: {}".format(result))
    yield session.leave()
    yield transport.close()

if __name__ == '__main__':
    import txaio
    txaio.start_logging(level='debug')
    component = Component(main=main, realm=u'crossbardemo')
    react(component.start)
