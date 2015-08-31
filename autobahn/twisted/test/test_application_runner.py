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
# t.i.reactor doesn't exist until we've imported it once, but we
# need it to exist so we can @patch it out in the tests ...
from twisted.internet import reactor  # noqa
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.internet.error import ConnectionRefusedError
from twisted.internet.interfaces import IStreamClientEndpoint, IProtocolFactory
from twisted.trial import unittest

from mock import patch, Mock

from autobahn.twisted.wamp import ApplicationRunner
from autobahn.wamp.test.test_runner import FakeReactor, FakeSession

import txaio


class TestWampTwistedRunner(unittest.TestCase):
    def test_connect_error(self, *args):
        '''
        Ensure the runner doesn't swallow errors and that it exits the
        reactor properly if there is one.
        '''
        exception = ConnectionRefusedError("It's a trap!")
        mockreactor = FakeReactor(exception)
        runner = ApplicationRunner('ws://localhost:1', 'realm', loop=mockreactor)

        self.assertRaises(
            ConnectionRefusedError,
            runner.run, FakeSession,
            start_reactor=True,
        )
        self.assertTrue(mockreactor.stop_called)


def raise_error(*args, **kw):
    raise RuntimeError("we always fail")


class TestApplicationRunner(unittest.TestCase):
    @patch('autobahn.twisted.wamp.log')
    @patch('twisted.internet.reactor')
    def test_runner_default(self, fakereactor, fakelog):
        fakereactor.connectTCP = Mock(side_effect=raise_error)
        runner = ApplicationRunner(u'ws://fake:1234/ws', u'dummy realm', loop=fakereactor)

        # we should get "our" RuntimeError when we call run
        self.assertRaises(RuntimeError, runner.run, raise_error)

        # making test general; if we got a "run()" we should also
        # get a "stop()"
        self.assertEqual(
            fakereactor.run.call_count,
            fakereactor.stop.call_count
        )

    @patch('autobahn.twisted.wamp.log')
    @patch('twisted.internet.reactor')
    @inlineCallbacks
    def test_runner_no_run(self, fakereactor, fakelog):
        fakereactor.connectTCP = Mock(side_effect=raise_error)
        runner = ApplicationRunner(u'ws://fake:1234/ws', u'dummy realm')

        try:
            yield runner.run(raise_error, start_reactor=False)
            self.fail()  # should have raise an exception, via Deferred

        except RuntimeError as e:
            # make sure it's "our" exception
            self.assertEqual(e.args[0], "we always fail")

        # neither reactor.run() NOR reactor.stop() should have been called
        # (just connectTCP() will have been called)
        self.assertEqual(fakereactor.run.call_count, 0)
        self.assertEqual(fakereactor.stop.call_count, 0)

    @patch('twisted.internet.reactor')
    def test_runner_no_run_happypath(self, fakereactor, fakelog):
        proto = Mock()
        fakereactor.connectTCP = Mock(return_value=succeed(proto))
        runner = ApplicationRunner(u'ws://fake:1234/ws', u'dummy realm')

        d = runner.run(Mock(), start_reactor=False)

        # shouldn't have actually connected to anything
        # successfully
        self.assertFalse(d.called)

        # neither reactor.run() NOR reactor.stop() should have been called
        # (just connectTCP() will have been called)
        self.assertEqual(fakereactor.run.call_count, 0)
        self.assertEqual(fakereactor.stop.call_count, 0)


class TestConnection(unittest.TestCase):
    """
    Connection is generic between asyncio and Twisted, however writing
    tests that work on both is "hard" due to differences in how
    faking out the event-loop works (and, e.g., the fact that
    asyncio needs you to "iterate" the event-loop some arbitrary
    number of times to get Future callbacks to "go").

    So, tests in this test-case should be "generic" in the sense
    of using txaio but can (and do) depend on Twisted reactor
    details to fake things out.
    """
    def setUp(self):
        self.config = dict()  # "should" be a ComponentConfig
        self.loop = FakeReactor(None)
        txaio.config.loop = self.loop
        self.session = FakeSession(self.config)
        # one generic transport for all tests
        self.transports = [{
            "type": "websocket",
            "url": "ws://localhost:9876/ws",
            "endpoint": {
                "type": "tcp",
                "host": "127.0.0.1",
                "port": 9876,
            }
        }]
        self.connection = Connection(self.session, self.transports, loop=self.loop)

    def test_failed_open(self):
        """If the connect fails, the future/deferred from .open() should fail"""
        d = self.connection.open()
        error = Exception("fake error")

        # pretend the connect call failed.
        txaio.reject(self.connection._connecting, error)

        # depending on Twisted impl. details here (i.e. won't work for Future)
        self.assertTrue(d.called)
        self.assertEqual(d.result.value, error)
        # we wanted this error, so ignore it
        txaio.add_callbacks(d, None, lambda _: None)

    def test_successful_open_and_disconnect(self):
        """future/deferred from .open() should callback after disconnect"""
        d = self.connection.open()

        # pretend the connect was successful
        txaio.resolve(self.connection._connecting, None)
        # ...and that we got the on_disconnect event
        self.connection._on_disconnect('closed')

        self.assertTrue(d.called)

    def test_successful_open_and_failed_transport(self):
        """If on_disconnect isn't clean, .open deferred/future should error"""
        d = self.connection.open()

        # pretend the connect was successful
        txaio.resolve(self.connection._connecting, None)
        # ...and that we got the on_disconnect event
        self.connection._on_disconnect('lost')

        self.assertTrue(d.called)
        # ignore this error; we expected it
        txaio.add_callbacks(d, None, lambda _: None)
        return d
