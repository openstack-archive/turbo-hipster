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

import os
import time
import uuid

import base
import fakes


class TestTaskRunner(base.TestWithGearman):
    def test_job_can_shutdown_th(self):
        self._load_config_fixture('jjb-config.yaml')
        self.start_server()
        zuul = fakes.FakeZuul(self.config['zuul_server']['gearman_host'],
                              self.config['zuul_server']['gearman_port'])

        job_uuid = str(uuid.uuid1())
        data_req = {
            'ZUUL_UUID': job_uuid,
            'ZUUL_PROJECT': 'stackforge/turbo-hipster',
            'ZUUL_PIPELINE': 'check',
            'ZUUL_URL': 'git://git.openstack.org/',
            'BRANCH': 'master',
            'BASE_LOG_PATH': '56/123456/8',
            'LOG_PATH': '56/123456/8/check/job_name/%s' % job_uuid
        }

        zuul.submit_job('build:gate-turbo-hipster-pep8', data_req)
        zuul.wait_for_completion()

        self.log.debug(zuul.job)
        asdf