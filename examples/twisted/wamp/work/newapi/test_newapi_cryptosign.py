import os
import binascii
import txaio

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from autobahn.twisted.component import Component, run
from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import CryptoSignAuthenticator, Session, IWampAuthenticationMethod
from zope.interface import implementer
import nacl

@implementer(IWampAuthenticationMethod)
class CustomAuthenticator(object):
    wamp_method_name = "cryptosign"  # how this will be advertised to the server

    def __init__(self):
        self._key = nacl.signing.SigningKey(b'\xdc\x13q\xc6\x17\x14\x11\xd2M\x14\x9a\xaf\x9b\xf6\xc8<\x12\x81\x86\x90\xf0D!F\x7f\xe3\x18\xb9\xa1O\x8d\xb7')

    def get_authextra(self):
        return {
            u'pubkey': self._key.verify_key.encode(nacl.encoding.HexEncoder).decode('ascii')
        }

    @inlineCallbacks
    def on_challenge(self, session, challenge):
        print("custom on_challenge", session, challenge)
        print("waiting 2 seconds")
        # obviously, you could do "whatever" here, e.g. look up database, call remote service, et.c
        yield sleep(2)
        # re-implement WAMP-Cryptosign, but w/o error-checking/handling
        challenge_hex = challenge.extra[u'challenge']
        challenge_raw = binascii.a2b_hex(challenge_hex)
        sig_raw = self._key.sign(challenge_raw)
        sig_hex = binascii.b2a_hex(sig_raw).decode('ascii')
        returnValue(sig_hex)

auth_config = {
    u"authid": u"alice",
    u"methods": [
        CustomAuthenticator(),
#        {
#            u"name": u"cryptosign",
#            u"key_data": b'\xdc\x13q\xc6\x17\x14\x11\xd2M\x14\x9a\xaf\x9b\xf6\xc8<\x12\x81\x86\x90\xf0D!F\x7f\xe3\x18\xb9\xa1O\x8d\xb7'
#        },
        {
            u"name": u"anonymous",
        },
    ],
}

#@inlineCallbacks
def setup_alice(reactor, session): ## What about details?
    print("setup alice", reactor, session)
    print("\n\nSUCCESS\nshutting down\n")
    return session.leave()

if __name__ == '__main__':
    transports = [
        {
            "type": "websocket",
            "url": "ws://127.0.0.1:8080/auth_ws"
        }
    ]

    component1 = Component(
        setup=setup_alice,
        transports=transports,
        realm=u'crossbardemo',
        authentication=auth_config,
    )
    component1.session_factory = Session
    txaio.start_logging(level='info')
    run([component1])#, log_level='info')
