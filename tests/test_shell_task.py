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
import json
import logging
import os
import uuid


class TestTaskRunner(base.TestWithGearman):
    log = logging.getLogger("TestTaskRunner")

    def test_simple_job_passes(self):
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

        zuul.submit_job('build:do_something_shelly', data_req)
        zuul.wait_for_completion()

        last_data = json.loads(zuul.job.data[-1])
        self.log.debug(last_data)

        self.assertTrue(zuul.job.complete)
        self.assertFalse(zuul.job.failure)
        self.assertEqual("SUCCESS", last_data['result'])

        task_output_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'task_output.log'
        ))

        self.assertIn("Step 1: Setup environment", task_output_file.readline())

        git_prep_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'git_prep.log'
        ))

        self.assertIn("gerrit-git-prep.sh", git_prep_file.readline())

        shell_output_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'shell_output.log'
        ))

        self.assertIn("ls -lah", shell_output_file.readline())

    def test_simple_job_fails(self):
        # Test when the script fails
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

        # Modify the job to fail. The git_path, job_working_dir and unqiue_id
        # are all passed to the shell script. If we 'ls unique_id' it'll fail
        # since it doesn't exist.
        self.config['plugins'][2]['shell_script'] = 'ls -lah'

        zuul.submit_job('build:do_something_shelly', data_req)
        zuul.wait_for_completion()

        last_data = json.loads(zuul.job.data[-1])
        self.log.debug(last_data)

        self.assertTrue(zuul.job.complete)
        self.assertTrue(zuul.job.failure)
        self.assertEqual("Return code from test script was non-zero (2)",
                         last_data['result'])

        task_output_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'task_output.log'
        ))

        self.assertIn("Step 1: Setup environment", task_output_file.readline())

        git_prep_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'git_prep.log'
        ))

        self.assertIn("gerrit-git-prep.sh", git_prep_file.readline())

        shell_output_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'shell_output.log'
        ))

        self.assertIn("ls -lah", shell_output_file.readline())

    def test_logs_uploaded_during_failure(self):
        # When turbo-hipster itself fails (eg analysing results) it should
        # still upload the python logging log if it can

        from turbo_hipster.lib.models import ShellTask
        def _fake_parse_and_check_results(*args, **kwargs):
            answer = this_should_fail

        ShellTask._parse_and_check_results = _fake_parse_and_check_results

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

        zuul.submit_job('build:do_something_shelly', data_req)
        zuul.wait_for_completion()

        last_data = json.loads(zuul.job.data[-1])
        self.log.debug(last_data)

        self.assertTrue(zuul.job.complete)
        self.assertTrue(zuul.job.failure)
        self.assertEqual("FAILURE running the job\n"
                         "Exception: global name 'this_should_fail' is not "
                         "defined", last_data['result'])

        git_prep_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'git_prep.log'
        ))

        self.assertIn("gerrit-git-prep.sh", git_prep_file.readline())

        shell_output_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'shell_output.log'
        ))

        self.assertIn("ls -lah", shell_output_file.readline())

        task_output_file = open(os.path.join(
            self.config['publish_logs']['path'], data_req['LOG_PATH'],
            'task_output.log'
        ))

        task_output_lines = task_output_file.readlines()
        self.assertIn("Step 1: Setup environment", task_output_lines[0])
        self.assertIn("Something failed running the job!",
                      task_output_lines[5])
        self.assertIn("NameError: global name 'this_should_fail' is not "
                      "defined", task_output_lines[13])

    def test_exception_when_uploading_fails(self):
        # When uploading fails the best we can do is return back

        from turbo_hipster.lib.models import Task
        def _fake_upload_results(*args, **kwargs):
            answer = this_should_fail

        Task._upload_results = _fake_upload_results

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

        zuul.submit_job('build:do_something_shelly', data_req)
        zuul.wait_for_completion()

        last_data = json.loads(zuul.job.data[-1])
        self.log.debug(last_data)

        self.assertTrue(zuul.job.complete)
        self.assertTrue(zuul.job.failure)
        self.assertEqual("FAILURE during cleanup and log upload\n"
                         "Exception: global name 'this_should_fail' is not "
                         "defined", last_data['result'])

    def test_failure_during_setup(self):
        pass
