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

import base
import fakes
import fixtures
import json
import logging
import os
import uuid

from turbo_hipster.lib import utils


class TestTaskRunner(base.TestWithGearman):
    log = logging.getLogger("TestTaskRunner")

    def _grab_jjb(self):
        # Grab a copy of JJB's config
        temp_path = self.useFixture(fixtures.TempDir()).path
        cmd = 'git clone git://git.openstack.org/openstack-infra/config'
        utils.execute_to_log(cmd, '/dev/null', cwd=temp_path)
        return os.path.join(
            temp_path, 'config',
            'modules/openstack_project/files/jenkins_job_builder/config'
        )

    def test_jjb_pep8_job(self):
        self.skipTest("This is buggy atm.")
        # We can only do this if we have the slave scripts installed in
        # /usr/local/jenkins/slave_scripts/
        if not os.path.isdir('/usr/local/jenkins/slave_scripts/'):
            self.skipTest("Slave scripts aren't installed")

        jjb_config_dir = self._grab_jjb()
        self._load_config_fixture('jjb-config.yaml')
        # set jjb_config to pulled in config
        self.config['plugins'][0]['jjb_config'] = jjb_config_dir

        self.start_server()
        zuul = fakes.FakeZuul(self.config['zuul_server']['gearman_host'],
                              self.config['zuul_server']['gearman_port'])

        job_uuid = str(uuid.uuid1())[:8]
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

        self.assertTrue(zuul.job.complete)
        last_data = json.loads(zuul.job.data[-1])
        self.log.debug(last_data)
        self.assertEqual("SUCCESS", last_data['result'])
