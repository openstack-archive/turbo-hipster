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
import gear
import logging
import os
import testtools
import time
import yaml

import turbo_hipster.worker_server

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestWithGearman(testtools.TestCase):

    log = logging.getLogger("TestWithGearman")

    def setUp(self):
        super(TestWithGearman, self).setUp()
        self.config = None
        self.worker_server = None
        self.gearman_server = gear.Server(0)

    def start_server(self):
        if not self.config:
            self._load_config_fixture()
        # Grab the port so the clients can connect to it
        self.config['zuul_server']['gearman_port'] = self.gearman_server.port

        self.worker_server = turbo_hipster.worker_server.Server(self.config)
        self.worker_server.setup_logging()
        self.worker_server.start()
        t0 = time.time()
        while time.time() - t0 < 10:
            if self.worker_server.services_started:
                break
            time.sleep(0.01)
        if not self.worker_server.services_started:
            self.fail("Failed to start worker_service services")

    def tearDown(self):
        if self.worker_server and not self.worker_server.stopped():
            self.worker_server.shutdown()
        self.gearman_server.shutdown()
        super(TestWithGearman, self).tearDown()

    def _load_config_fixture(self, config_name='default-config.yaml'):
        config_dir = os.path.join(os.path.dirname(__file__), 'etc')
        with open(os.path.join(config_dir, config_name), 'r') as config_stream:
            self.config = yaml.safe_load(config_stream)

        # Set all of the working dirs etc to a writeable temp dir
        temp_path = self.useFixture(fixtures.TempDir()).path
        for config_dir in ['debug_log', 'jobs_working_dir', 'git_working_dir',
                           'pip_download_cache']:
            if config_dir in self.config:
                if self.config[config_dir][0] == '/':
                    self.config[config_dir] = self.config[config_dir][1:]
                self.config[config_dir] = os.path.join(temp_path,
                                                       self.config[config_dir])
        if self.config['publish_logs']['type'] == 'local':
            if self.config['publish_logs']['path'][0] == '/':
                self.config['publish_logs']['path'] = \
                    self.config['publish_logs']['path'][1:]
            self.config['publish_logs']['path'] = os.path.join(
                temp_path, self.config[config_dir])
