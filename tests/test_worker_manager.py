#!/usr/bin/python2
#
# Copyright 2013 Rackspace Australia
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


import json
import os
import testtools
import time
from fakes import FakeGearmanManager, FakeGearmanServer, FakeRealDbUpgradeRunner

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'etc')
with open(os.path.join(CONFIG_DIR, 'config.json'), 'r') as config_stream:
    CONFIG = json.load(config_stream)


class TestGearmanManager(testtools.TestCase):
    def setUp(self):
        super(TestGearmanManager, self).setUp()
        self.config = CONFIG
        self.gearman_server = FakeGearmanServer(
            self.config['zuul_server']['gearman_port'])
        self.config['zuul_server']['gearman_port'] = self.gearman_server.port

        self.task = FakeRealDbUpgradeRunner(self.config, self)
        self.tasks = dict(FakeRealDbUpgradeRunner_worker=self.task)

        self.gearman_manager = FakeGearmanManager(self.config,
                                                  self.tasks,
                                                  self)

    def test_manager_function_registered(self):
        """ Check the manager is set up correctly and registered with the
        gearman server with an appropriate function """

        # Give the gearman server up to 5 seconds to register the function
        for x in range(500):
            time.sleep(0.01)
            if len(self.gearman_server.functions) > 0:
                break

        hostname = os.uname()[1]
        function_name = 'stop:turbo-hipster-manager-%s' % hostname

        self.assertIn(function_name, self.gearman_server.functions)

    def test_task_registered_with_manager(self):
        """ Check the FakeRealDbUpgradeRunner_worker task is registered """
        self.assertIn('FakeRealDbUpgradeRunner_worker',
                      self.gearman_manager.tasks.keys())

    def test_stop_task(self):
        """ Check that the manager successfully stops a task when requested
        """
        pass

if __name__ == '__main__':
    unittest.main()
