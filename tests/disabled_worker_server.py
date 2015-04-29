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


import os
import testtools
import yaml

from turbo_hipster import worker_server

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'etc')
with open(os.path.join(CONFIG_DIR, 'config.yaml'), 'r') as config_stream:
    CONFIG = yaml.safe_load(config_stream)

CONF_D_DIR = os.path.join(CONFIG_DIR, "conf.d")


class TestServerManager(testtools.TestCase):
    def setUp(self):
        super(TestServerManager, self).setUp()
        self.config = CONFIG

    def tearDown(self):
        super(TestServerManager, self).tearDown()

    def test_confd_configuration(self):
        """ Check that the server can load in other configuration from a
        conf.d directory """

        def pass_function(*args, **kargs):
            pass

        self.config["conf_d"] = CONF_D_DIR

        worker_server.Server.setup_logging = pass_function
        serv = worker_server.Server(self.config)
        serv_config = serv.config
        self.assertIn("extra_configuration", serv_config)
        self.assertEquals("testing123", serv_config["extra_configuration"])
