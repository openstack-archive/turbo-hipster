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


import gear
import json
import logging
import os
import testtools
import time

import turbo_hipster.task_plugins.gate_real_db_upgrade.task
import turbo_hipster.worker_server


logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestWithGearman(testtools.TestCase):

    log = logging.getLogger("TestWithGearman")

    def setUp(self):
        super(TestWithGearman, self).setUp()

        self.config = []
        self._load_config_fixture()

        self.gearman_server = gear.Server(0)

        # Grab the port so the clients can connect to it
        self.config['zuul_server']['gearman_port'] = self.gearman_server.port

        self.worker_server = turbo_hipster.worker_server.Server(self.config)
        self.worker_server.start()
        t0 = time.time()
        while time.time() - t0 < 10:
            if self.worker_server.services_started:
                break
            time.sleep(0.01)
        if not self.worker_server.services_started:
            self.fail("Failed to start worker_service services")

    def tearDown(self):
        self.worker_server.stop()
        self.gearman_server.shutdown()
        super(TestWithGearman, self).tearDown()

    def _load_config_fixture(self, config_name='default-config.json'):
        config_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        with open(os.path.join(config_dir, config_name), 'r') as config_stream:
            self.config = json.load(config_stream)


class TestWorkerServer(TestWithGearman):
    def test_plugins_load(self):
        "Test the configured plugins are loaded"

        self.assertFalse(self.worker_server.stopped())
        self.assertEqual(3, len(self.worker_server.plugins))

        plugin0_config = {
            "name": "gate_real_db_upgrade",
            "datasets_dir": "/var/lib/turbo-hipster/datasets_devstack_131007",
            "function": "build:gate-real-db-upgrade_nova_mysql_devstack_131007"
        }
        plugin1_config = {
            "name": "gate_real_db_upgrade",
            "datasets_dir": "/var/lib/turbo-hipster/datasets_user_001",
            "function": "build:gate-real-db-upgrade_nova_mysql_user_001"
        }
        plugin2_config = {
            "name": "shell_script",
            "function": "build:do_something_shelly"
        }

        self.assertEqual(plugin0_config,
                         self.worker_server.plugins[0]['plugin_config'])
        self.assertEqual(
            'turbo_hipster.task_plugins.gate_real_db_upgrade.task',
            self.worker_server.plugins[0]['module'].__name__
        )

        self.assertEqual(plugin1_config,
                         self.worker_server.plugins[1]['plugin_config'])
        self.assertEqual(
            'turbo_hipster.task_plugins.gate_real_db_upgrade.task',
            self.worker_server.plugins[1]['module'].__name__
        )

        self.assertEqual(plugin2_config,
                         self.worker_server.plugins[2]['plugin_config'])
        self.assertEqual(
            'turbo_hipster.task_plugins.shell_script.task',
            self.worker_server.plugins[2]['module'].__name__
        )

    def test_zuul_client_started(self):
        "Test the zuul client has been started"
        self.assertFalse(self.worker_server.zuul_client.stopped())

    def test_zuul_manager_started(self):
        "Test the zuul manager has been started"
        self.assertFalse(self.worker_server.zuul_manager.stopped())


class TestZuulClient(TestWithGearman):
    def test_setup_gearman_worker(self):
        "Make sure the client is registered as a worker with gearman"
        pass

    def test_registered_functions(self):
        "Test the correct functions are registered with gearman"
        # The client should have all of the functions defined in the config
        # registered with gearman

        # We need to wait for all the functions to register with the server..
        # We'll give it up to 10seconds to do so
        t0 = time.time()
        failed = True
        while time.time() - t0 < 10:
            # There should be 4 functions. 1 for each plugin + 1 for the
            # manager
            if len(self.gearman_server.functions) == 4:
                failed = False
                break
            time.sleep(0.01)
        if failed:
            self.log.debug(self.gearman_server.functions)
            self.fail("The correct number of functions haven't registered with"
                      " gearman")

        self.assertIn('build:gate-real-db-upgrade_nova_mysql_devstack_131007',
                      self.gearman_server.functions)
        self.assertIn('build:gate-real-db-upgrade_nova_mysql_user_001',
                      self.gearman_server.functions)
        self.assertIn('build:do_something_shelly',
                      self.gearman_server.functions)

    def test_waiting_for_job(self):
        "Make sure the client waits for jobs as expected"
        pass

    def test_stop(self):
        "Test sending a stop signal to the client exists correctly"
        pass

"""
class TestZuulManager(TestWithGearman):
    def test_registered_functions(self):
        "Test the correct functions are registered with gearman"
        # We need to wait for all the functions to register with the server..
        # We'll give it up to 10seconds to do so
        t0 = time.time()
        failed = True
        while time.time() - t0 < 10:
            # There should be 4 functions. 1 for each plugin + 1 for the
            # manager
            if len(self.gearman_server.functions) == 4:
                failed = False
                break
            time.sleep(0.01)
        if failed:
            self.log.debug(self.gearman_server.functions)
            self.fail("The correct number of functions haven't registered with"
                      " gearman")

        hostname = os.uname()[1]
        self.assertIn('stop:turbo-hipster-manager-%s' % hostname,
                      self.gearman_server.functions)
"""
