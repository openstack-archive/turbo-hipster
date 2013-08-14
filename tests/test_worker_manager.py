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
from fakes import FakeGearmanManager, FakeGearmanServer

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'etc')
with open(os.path.join(CONFIG_DIR, 'config.json'), 'r') as config_stream:
    CONFIG = json.load(config_stream)


class TestGearmanManager(testtools.TestCase):
    def setUp(self):
        super(TestGearmanManager, self).setUp()
        self.config = CONFIG
        self.tasks = []
        self.gearman_server = FakeGearmanServer(
            self.config['zuul_server']['gearman_port'])

        self.gearman_manager = FakeGearmanManager(self.config,
                                                  self.tasks,
                                                  self)

    def test_manager_function_registered(self):
        """ Check the manager is set up correctly and registered with the
        gearman server with an appropriate function """
        pass

if __name__ == '__main__':
    unittest.main()
