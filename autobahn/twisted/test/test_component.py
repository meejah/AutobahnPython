###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) Tavendo GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################

from __future__ import absolute_import

import os
import unittest
from mock import Mock, patch

if os.environ.get('USE_TWISTED', False):
    from autobahn.twisted.component import Component
    from zope.interface import directlyProvides
    from autobahn.wamp.message import Welcome, Goodbye
    from autobahn.wamp.serializer import JsonSerializer
    from twisted.internet.interfaces import IStreamClientEndpoint
    from twisted.internet.defer import inlineCallbacks, succeed

    class ConnectionTests(unittest.TestCase):

        def setUp(self):
            pass

        @patch('autobahn.twisted.component.sleep', return_value=succeed(None))
        @inlineCallbacks
        def test_successful_connect(self, fake_sleep):
            endpoint = Mock()
            proto = Mock()
            joins = []

            def joined(session, details):
                joins.append((session, details))
                return session.leave()
            directlyProvides(endpoint, IStreamClientEndpoint)
            component = Component(
                transports={
                    "type": "websocket",
                    "url": "ws://127.0.0.1/ws",
                    "endpoint": endpoint,
                }
            )
            component.on('join', joined)
            reactor = Mock()

            def connect(factory, **kw):
                print("connect", factory, kw)
                proto = factory.buildProtocol('boom')
                proto.makeConnection(Mock())
                #proto.peer = Mock()

                from autobahn.websocket.protocol import WebSocketProtocol
                from base64 import b64encode
                from hashlib import sha1
                key = proto.websocket_key + WebSocketProtocol._WS_MAGIC
                proto.data = (
                    b"HTTP/1.1 101 Switching Protocols\x0d\x0a"
                    b"Upgrade: websocket\x0d\x0a"
                    b"Connection: upgrade\x0d\x0a"
                    b"Sec-Websocket-Protocol: wamp.2.json\x0d\x0a"
                    b"Sec-Websocket-Accept: " + b64encode(sha1(key).digest()) + b"\x0d\x0a\x0d\x0a"
                )
                proto.processHandshake()
                print("DING", proto.state)

                from autobahn.wamp import role
                features = role.RoleBrokerFeatures(
                    publisher_identification=True,
                    pattern_based_subscription=True,
                    session_meta_api=True,
                    subscription_meta_api=True,
                    subscriber_blackwhite_listing=True,
                    publisher_exclusion=True,
                    subscription_revocation=True,
                    payload_transparency=True,
                    payload_encryption_cryptobox=True,
                )

                msg = Welcome(123456, dict(broker=features), realm=u'realm')
                serializer = JsonSerializer()
                data, is_binary = serializer.serialize(msg)
                print("DATA", is_binary)
                #proto.dataReceived(data)
                proto.onMessage(data, is_binary)

#                proto.dataReceived(b'asdfasdf')
                print("proto", proto, proto.state)

                msg = Goodbye()
                proto.onMessage(*serializer.serialize(msg))
                proto.onClose(True, 100, "some old reason")

                return succeed(proto)
            endpoint.connect = connect

            print("connecting")
            d = component.start()#reactor)
            print("XXX", d)
            x = yield d
            print("OHAI!", x)
            self.assertTrue(len(joins), 1)
            print("JOINS", joins)


    class InvalidTransportConfigs(unittest.TestCase):

        def test_invalid_key(self):
            with self.assertRaises(ValueError) as ctx:
                # XXX can probably get rid of main= thing?
                Component(
                    main=lambda r, s: None,
                    transports=dict(
                        foo='bar',  # totally invalid key
                    ),
                )
            self.assertIn("'foo' is not", str(ctx.exception))

        def test_invalid_key_transport_list(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        dict(type='websocket', url='ws://127.0.0.1/ws'),
                        dict(foo='bar'),  # totally invalid key
                    ]
                )
            self.assertIn("'foo' is not a valid configuration item", str(ctx.exception))

        def test_invalid_serializer_key(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "url": "ws://127.0.0.1/ws",
                            "serializer": ["quux"],
                        }
                    ]
                )
            self.assertIn("only for rawsocket", str(ctx.exception))

        def test_invalid_serializer(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "url": "ws://127.0.0.1/ws",
                            "serializers": ["quux"],
                        }
                    ]
                )
            self.assertIn("Invalid serializer", str(ctx.exception))

        def test_invalid_serializer_type_0(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "url": "ws://127.0.0.1/ws",
                            "serializers": [1, 2],
                        }
                    ]
                )
            self.assertIn("must be a list", str(ctx.exception))

        def test_invalid_serializer_type_1(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "url": "ws://127.0.0.1/ws",
                            "serializers": 1,
                        }
                    ]
                )
            self.assertIn("must be a list", str(ctx.exception))

        def test_invalid_type_key(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "type": "bad",
                        }
                    ]
                )
            self.assertIn("Invalid transport type", str(ctx.exception))

        def test_invalid_type(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        "foo"
                    ]
                )
            self.assertIn("must be a dict", str(ctx.exception))

        def test_no_url(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "type": "websocket",
                        }
                    ]
                )
            self.assertIn("Transport requires 'url'", str(ctx.exception))

        def test_endpoint_bogus_object(self):
            with self.assertRaises(ValueError) as ctx:
                Component(
                    main=lambda r, s: None,
                    transports=[
                        {
                            "type": "websocket",
                            "url": "ws://example.com/ws",
                            "endpoint": ("not", "a", "dict"),
                        }
                    ]
                )
            self.assertIn("'endpoint' configuration must be", str(ctx.exception))

        def test_endpoint_valid(self):
            Component(
                main=lambda r, s: None,
                transports=[
                    {
                        "type": "websocket",
                        "url": "ws://example.com/ws",
                        "endpoint": {
                            "type": "tcp",
                            "host": "1.2.3.4",
                            "port": "4321",
                        }
                    }
                ]
            )
