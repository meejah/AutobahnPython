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

import txaio

from autobahn.wamp.interfaces import ISession
from autobahn.wamp.protocol import _ListenerCollection
from autobahn.wamp.runner import Connection


class FakeSession(object):
    def __init__(self, config):
        self.config = config
        self.on = _ListenerCollection(['join', 'leave', 'ready', 'connect', 'disconnect'])
    def onOpen(self, *args, **kw):
        print('onOpen', args, kw)


ISession.register(FakeSession)


if os.environ.get('USE_TWISTED', False):
    from zope.interface import implementer
    from twisted.internet.defer import maybeDeferred
    from twisted.internet.interfaces import IReactorTime, IReactorCore

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
