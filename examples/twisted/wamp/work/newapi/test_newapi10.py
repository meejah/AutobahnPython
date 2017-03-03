
# run multiple WAMP sessions over the same underlying WAMP transport


# this could be accomplished with a session.split(), perhaps?
# (maybe this and test_newapi8.py want to have something like
#  session.get_transport() or so, sand levae transport.split()?)

session1 = ApplicationSession()
session2 = ApplicationSession()


def main(reactor, transport):
    transport1 = yield transport.split()
    session = yield transport.join()
    yield session1.join(transport, u'myrealm1')
    yield session2.join(transport, u'myrealm1')


def main1(reactor, transport):
    yield session1.join(transport, u'myrealm1')

def main2(reactor, transport):
    yield session2.join(transport, u'myrealm1')


if __name__ == '__main__':

    transports = [
        {
            'type': 'rawsocket',
            'serializer': 'msgpack',
            'endpoint': {
                'type': 'unix',
                'path': '/tmp/cb1.sock'
            }
        }
    ]

    realm = u'myrealm1'

    extra = {
        u'foo': 23,
        u'bar': u'baz'
    }

    client = Client([main1, main2])
    react(connection.start)



#
# Session
# Transport
# Connection
# Component
# Service
# Client
#
#
