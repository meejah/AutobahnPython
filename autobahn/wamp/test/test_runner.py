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

from __future__ import absolute_import, print_function

import os
import unittest2 as unittest

from mock import patch
from autobahn.wamp.interfaces import ISession
from autobahn.wamp.protocol import _ListenerCollection


class FakeSession(object):
    def __init__(self, config):
        self.config = config
        self.on = _ListenerCollection(['join', 'leave', 'ready', 'connect', 'disconnect'])
ISession.register(FakeSession)


if os.environ.get('USE_TWISTED', False):
    from autobahn.twisted.wamp import ApplicationRunner
    from twisted.internet.defer import maybeDeferred
    from twisted.internet.interfaces import IReactorTime, IReactorCore
    from twisted.internet.error import ConnectionRefusedError
    from zope.interface import implementer

    @implementer(IReactorTime, IReactorCore)
    class FakeReactor(object):
        '''
        This just fakes out enough reactor methods so .run() can work.
        '''
        stop_called = False
        running = True

        def __init__(self, to_raise):
            self.stop_called = False
            self.to_raise = to_raise
            self.delayed = []
            self.when_running = []

        def run(self, *args, **kw):
            for d in self.when_running:
                d.errback(self.to_raise)

        def stop(self):
            self.stop_called = True

        def callLater(self, delay, func, *args, **kwargs):
            self.delayed.append((delay, func, args, kwargs))

        def connectTCP(self, *args, **kw):
            pass

        def callWhenRunning(self, method, *args, **kw):
            d = maybeDeferred(method, *args, **kw)
            self.when_running.append(d)

    @patch('autobahn.twisted.wamp.log')
    class TestWampTwistedRunner(unittest.TestCase):
        def test_connect_error(self, *args):
            '''
            Ensure the runner doesn't swallow errors and that it exits the
            reactor properly if there is one.
            '''
            try:
                from autobahn.twisted.wamp import ApplicationRunner
                from twisted.internet.error import ConnectionRefusedError
                # the 'reactor' member doesn't exist until we import it
                from twisted.internet import reactor  # noqa: F401
            except ImportError:
                raise unittest.SkipTest('No twisted')

            exception = ConnectionRefusedError("It's a trap!")
            mockreactor = FakeReactor(exception)
            runner = ApplicationRunner('ws://localhost:1', 'realm', loop=mockreactor)

            self.assertRaises(
                ConnectionRefusedError,
                runner.run, FakeSession,
                start_reactor=True,
            )
            self.assertTrue(mockreactor.stop_called)

else:
    # Asyncio tests.
    try:
        import asyncio
        from unittest.mock import patch, Mock
    except ImportError:
        # Trollius >= 0.3 was renamed to asyncio
        # noinspection PyUnresolvedReferences
        import trollius as asyncio
        from mock import patch, Mock
    from autobahn.asyncio.wamp import ApplicationRunner

    class TestApplicationRunner(unittest.TestCase):
        '''
        Test the autobahn.asyncio.wamp.ApplicationRunner class.
        '''
        def _assertRaisesRegex(self, exception, error, *args, **kw):
            try:
                self.assertRaisesRegex
            except AttributeError:
                f = self.assertRaisesRegexp
            else:
                f = self.assertRaisesRegex
            f(exception, error, *args, **kw)

        def test_explicit_SSLContext(self):
            '''
            Ensure that loop.create_connection is called with the exact SSL
            context object that is passed (as ssl) to the __init__ method of
            ApplicationRunner.
            '''
            loop = Mock()
            loop.run_until_complete = Mock(return_value=(Mock(), Mock()))
            ssl_context = object()
            transports = [
                {
                    "type": "websocket",
                    "url": "ws://localhost:8080/ws",
                    "endpoint": {
                        "type": "tcp",
                        "host": "127.0.0.1",
                        "port": 8080,
                        "tls": ssl_context,
                    },
                },
            ]
            runner = ApplicationRunner(
                'ws://127.0.0.1:8080/ws', 'realm',
                loop=loop,
            )
            runner.run(FakeSession)
            self.assertIs(ssl_context, loop.create_connection.call_args[1]['ssl'])

        def test_omitted_SSLContext_insecure(self):
            '''
            Ensure that loop.create_connection is called with ssl=False
            if no ssl argument is passed to the __init__ method of
            ApplicationRunner and the websocket URL starts with "ws:".
            '''
            loop = Mock()
            loop.run_until_complete = Mock(return_value=(Mock(), Mock()))
            with patch.object(asyncio, 'get_event_loop', return_value=loop):
                runner = ApplicationRunner(u'ws://127.0.0.1:8080/ws', u'realm')
                runner.run('_unused_')
                self.assertIs(False, loop.create_connection.call_args[1]['ssl'])

        def test_omitted_SSLContext_secure(self):
            '''
            Ensure that loop.create_connection is called with ssl=True
            if no ssl argument is passed to the __init__ method of
            ApplicationRunner and the websocket URL starts with "wss:".
            '''
            loop = Mock()
            loop.run_until_complete = Mock(return_value=(Mock(), Mock()))
            with patch.object(asyncio, 'get_event_loop', return_value=loop):
                runner = ApplicationRunner(u'wss://127.0.0.1:8080/wss', u'realm')
                runner.run('_unused_')
                self.assertIs(True, loop.create_connection.call_args[1]['ssl'])

        def test_conflict_SSL_True_with_ws_url(self):
            '''
            ApplicationRunner must raise an exception if given an ssl value of True
            but only a "ws:" URL.
            '''
            loop = Mock()
            loop.run_until_complete = Mock(return_value=(Mock(), Mock()))
            with patch.object(asyncio, 'get_event_loop', return_value=loop):
                runner = ApplicationRunner(u'ws://127.0.0.1:8080/wss', u'realm',
                                           ssl=True)
                error = ('^ssl argument value passed to ApplicationRunner '
                         'conflicts with the "ws:" prefix of the url '
                         'argument\. Did you mean to use "wss:"\?$')
                self._assertRaisesRegex(Exception, error, runner.run, '_unused_')

        def test_conflict_SSLContext_with_ws_url(self):
            '''
            ApplicationRunner must raise an exception if given an ssl value that is
            an instance of SSLContext, but only a "ws:" URL.
            '''
            import ssl
            try:
                # Try to create an SSLContext, to be as rigorous as we can be
                # by avoiding making assumptions about the ApplicationRunner
                # implementation. If we happen to be on a Python that has no
                # SSLContext, we pass ssl=True, which will simply cause this
                # test to degenerate to the behavior of
                # test_conflict_SSL_True_with_ws_url (above). In fact, at the
                # moment (2015-05-10), none of this matters because the
                # ApplicationRunner implementation does not check to require
                # that its ssl argument is either a bool or an SSLContext. But
                # that may change, so we should be careful.
                ssl.create_default_context
            except AttributeError:
                context = True
            else:
                context = ssl.create_default_context()

            loop = Mock()
            loop.run_until_complete = Mock(return_value=(Mock(), Mock()))
            with patch.object(asyncio, 'get_event_loop', return_value=loop):
                runner = ApplicationRunner(u'ws://127.0.0.1:8080/wss', u'realm',
                                           ssl=context)
                error = ('^ssl argument value passed to ApplicationRunner '
                         'conflicts with the "ws:" prefix of the url '
                         'argument\. Did you mean to use "wss:"\?$')
                self._assertRaisesRegex(Exception, error, runner.run, '_unused_')
