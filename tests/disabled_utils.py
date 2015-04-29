#!/usr/bin/python2
#
# Copyright 2014 Rackspace Australia
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import fixtures
import logging
import os
import testtools

from turbo_hipster.lib import utils


class TestExecuteToLog(testtools.TestCase):
    def test_makes_dir(self):
        tempdir = self.useFixture(fixtures.TempDir()).path
        self.assertFalse(os.path.exists(os.path.join(tempdir, 'foo')))
        utils.execute_to_log('echo yay',
                             os.path.join(tempdir, 'foo', 'banana.log'),
                             watch_logs=[])
        self.assertTrue(os.path.exists(os.path.join(tempdir, 'foo')))

    def test_logging_works(self):
        # Setup python logging to do what we need
        logging.basicConfig(format='%(asctime)s %(name)s %(message)s',
                            level=logging.DEBUG)

        tempdir = self.useFixture(fixtures.TempDir()).path
        log_path = os.path.join(tempdir, 'banana.log')

        utils.execute_to_log('echo yay', log_path, watch_logs=[])
        self.assertTrue(os.path.exists(log_path))

        with open(log_path) as f:
            d = f.read()
            print d

        self.assertNotEqual('', d)
        self.assertEqual(4, len(d.split('\n')))
        self.assertNotEqual(-1, d.find('yay'))
        self.assertNotEqual(-1, d.find('[script exit code = 0]'))

    def test_timeout(self):
        # Setup python logging to do what we need
        logging.basicConfig(format='%(asctime)s %(name)s %(message)s',
                            level=logging.DEBUG)

        tempdir = self.useFixture(fixtures.TempDir()).path
        log_path = os.path.join(tempdir, 'banana.log')

        utils.execute_to_log('/bin/sleep 30', log_path, watch_logs=[],
                             timeout=0.1)
        self.assertTrue(os.path.exists(log_path))

        with open(log_path) as f:
            d = f.read()
            print d

        self.assertNotEqual('', d)
        self.assertNotEqual(-1, d.find('[timeout]'))
        self.assertNotEqual(-1, d.find('[script exit code = -9]'))
