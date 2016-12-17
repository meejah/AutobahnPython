from autobahn.wamp import Api

# create an API object to use the decorator style
# register/subscribe WAMP actions

# note: this isn't there -- could use decorator-style methods on
# Component (e.g. @component.register(..) etc)
api = Api()

@api.register(u'com.example.add2')
def add2(a, b):
    return a + b

@api.subscribe(u'com.example.on-hello', details=True)
def on_hello(msg, details=None):
    print(u'Someone said: {}'.format(msg))
    details.session.leave()

@coroutine
def component1(session, details):
    # expose the API on the session
    yield session.expose(api)


@coroutine
def component2(reactor, session):
    """
    A second component, which gets called "main-like".
    When it returns, this will automatically close the session.
    """
    result = yield session.call(u'com.example.add2', 2, 3)
    session.publish(u'com.example.on-hello', u'result={}'.format(result))


if __name__ == '__main__':
    from autobahn.twisted.component import Component, run

    # Components wrap either a setup or main function and
    # can be configured with transports, authentication and so on.
    comp1 = Component()
    comp1.on('join', component1)

    # note: might be worth adding 'on_join=' optional kwargs to
    # Component so that you can do above definition "inline" in the
    # list below (e.g. Component(on_join=component1)

    components = [
        comp1,
        Component(main=component2)
    ]

    # a convenience runner is provided which takes a list of
    # components and runs all of them
    run(components)
