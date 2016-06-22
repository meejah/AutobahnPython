import os
import txaio

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from autobahn.twisted.component import Component, run
from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import CryptoSignAuthenticator, Session


#@inlineCallbacks
def setup_alice(reactor, session): ## What about details?
    print("setup alice", reactor, session)


if __name__ == '__main__':
    transports = [
        {
            "type": "websocket",
            "url": "ws://127.0.0.1:8080/auth_ws"
        }
    ]
    auth_config = {
        u"authid": u"alice",
        u"methods": [
            {
                u"name": u"cryptosign",
                u"key_data": b'\xdc\x13q\xc6\x17\x14\x11\xd2M\x14\x9a\xaf\x9b\xf6\xc8<\x12\x81\x86\x90\xf0D!F\x7f\xe3\x18\xb9\xa1O\x8d\xb7'
            }
        ],
    }

    component1 = Component(
        setup=setup_alice,
        transports=transports,
        realm=u'crossbardemo',
        authentication=auth_config,
    )
    component1.session_factory = Session
    txaio.start_logging(level='info')
    run([component1])#, log_level='info')
