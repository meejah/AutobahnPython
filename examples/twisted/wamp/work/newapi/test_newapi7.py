from twisted.internet.task import react
from twisted.internet.defer import inlineCallbacks as coroutine
from autobahn.twisted.component import Component, run


component = Component(realm=u'crossbardemo')

@component.on_join
def on_join(session, details):
    print("Session {} has joined: {}".format(details.session, details))

@component.on_leave
def on_leave(session, details):
    print("Session has left: {}".format(details))

@component.register(u'com.myapp.add2')  # registering in on_join
def add2(a, b):
    return a + b

@react
def main(reactor):
    return run(component)
