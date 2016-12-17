from twisted.internet.defer import inlineCallbacks as coroutine
from autobahn.twisted.util import sleep

@coroutine
def component1_setup(session, details):
    # the session is joined and ready for use.
    def shutdown():
        print('backend component: shutting down ..')
        session.leave()

    yield session.subscribe(shutdown, u'com.example.shutdown')
#    yield session.subscribe(u'com.example.shutdown', shutdown)

    def add2(a, b):
        print('backend component: add2()')
        return a + b

    yield session.register(add2, u'com.example.add2')
#    yield session.register(u'com.example.add2', add2)

    print('backend component: ready.')

    # as we exit, this signals we are ready! the session must be kept.


@coroutine
def component2_main(reactor, session):
    # the session is joined and ready
    yield sleep(.2)  # "enforce" order: backend must have started before we call it
    print('frontend component: ready')

    result = yield session.call(u'com.example.add2', 2, 3)
    print('frontend component: result={}'.format(result))

    session.publish(u'com.example.shutdown')

    # as we exit, this signals we are done with the session! the session
    # can be recycled
    print('frontend component: shutting down ..')


if __name__ == '__main__':
    from twisted.internet.task import react
    from autobahn.twisted.component import Component, run

    transports = [
        {
            'type': 'rawsocket',
            'url': 'ws://127.0.0.1:8080/ws',
            'serializer': 'msgpack',
            'endpoint': {
                'type': 'unix',
                'path': '/tmp/cb1.sock'
            }
        },
        {
            'type': 'websocket',
            'url': 'ws://127.0.0.1:8080/ws',
            'endpoint': {
                'type': 'tcp',
                'host': '127.0.0.1',
                'port': 8080
            }
        }
    ]

    config = {
        'realm': u'realm1',
        'extra': {
            'foo': 23
        }
    }

    comp1 = Component(transports=transports, config=config, realm=u'crossbardemo')
    comp1.on('join', component1_setup)
    components = [
        comp1,
        Component(main=component2_main, transports=transports, config=config, realm=u'crossbardemo')
    ]

    run(components)
