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
from twisted.internet.interfaces import IStreamClientEndpoint, IProtocolFactory
from twisted.trial import unittest

from mock import patch, Mock

from autobahn.twisted.wamp import ApplicationRunner

from mock import patch
from autobahn.twisted.wamp import ApplicationRunner

from autobahn.wamp.test.test_runner import FakeReactor, FakeSession

from autobahn.twisted.wamp import ApplicationRunner
from twisted.internet.error import ConnectionRefusedError

@patch('autobahn.twisted.wamp.log')
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

    @patch('autobahn.twisted.wamp.log')
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
