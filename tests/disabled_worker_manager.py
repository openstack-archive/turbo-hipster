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

import base
import fakes


class TestWorkerServer(base.TestWithGearman):
    def test_jobs_load_from_legacy_plugins(self):
        "Test the configured plugins are loaded from legacy config.yaml layout"

        self.start_server()

        self.assertFalse(self.worker_server.stopped())
        self.assertEqual(3, len(self.worker_server.jobs))

        expected_jobs = {
            'build:real-db-upgrade_nova_mysql_devstack_131007': {
                "name": "build:real-db-upgrade_nova_mysql_devstack_131007",
                "plugin": "real_db_upgrade",
                "runner_module_name": "turbo_hipster.task_plugins."
                                      "real_db_upgrade.task",
                "plugin_config": {
                    "name": "real_db_upgrade",
                    "datasets_dir": "/var/lib/turbo-hipster/"
                                    "datasets_devstack_131007",
                    "function": "build:real-db-upgrade_nova_mysql_devstack_"
                                "131007"
                },
            },
            'build:real-db-upgrade_nova_mysql_user_001': {
                "name": "build:real-db-upgrade_nova_mysql_user_001",
                "plugin": "real_db_upgrade",
                "runner_module_name": "turbo_hipster.task_plugins."
                                      "real_db_upgrade.task",
                "plugin_config": {
                    "name": "real_db_upgrade",
                    "datasets_dir": "/var/lib/turbo-hipster/datasets_user_001",
                    "function": "build:real-db-upgrade_nova_mysql_user_001"
                },
            },
            'build:do_something_shelly': {
                "name": "build:do_something_shelly",
                "plugin": "shell_script",
                "runner_module_name": "turbo_hipster.task_plugins."
                                      "shell_script.task",
                "job_config": {
                    "name": "build:do_something_shelly",
                    "shell_script": "ls -lah && echo",
                },
            },
        }

        for job_name, job in self.worker_server.jobs.items():
            self.assertEqual(expected_jobs[job_name]['name'],
                             job['name'])
            self.assertEqual(expected_jobs[job_name]['plugin'],
                             job['plugin'])
            if 'plugin_config' in job:
                self.assertEqual(expected_jobs[job_name]['plugin_config'],
                                 job['plugin_config'])
            if 'job_config' in job:
                self.assertEqual(expected_jobs[job_name]['job_config'],
                                 job['job_config'])
            self.assertEqual(
                expected_jobs[job_name]['runner_module_name'],
                job['runner'].__module__
            )

    def test_job_configuration(self):
        "Test config.yaml job layout"
        self._load_config_fixture('config.yaml')
        self.start_server()

        self.assertFalse(self.worker_server.stopped())
        self.assertEqual(3, len(self.worker_server.jobs))

        expected_jobs = {
            'build:real-db-upgrade_nova_mysql': {
                "name": "build:real-db-upgrade_nova_mysql",
                "plugin": "real_db_upgrade",
                "runner_module_name": "turbo_hipster.task_plugins."
                                      "real_db_upgrade.task",
                "job_config": {
                    "name": "build:real-db-upgrade_nova_mysql",
                    "plugin": "real_db_upgrade",
                    "datasets_dir": "/home/josh/var/lib/turbo-hipster/datasets"
                },
            },
            'build:real-db-upgrade_nova_mysql_user_001': {
                "name": "build:real-db-upgrade_nova_mysql_user_001",
                "plugin": "real_db_upgrade",
                "runner_module_name": "turbo_hipster.task_plugins."
                                      "real_db_upgrade.task",
                "plugin_config": {
                    "name": "real_db_upgrade",
                    "datasets_dir": "/var/lib/turbo-hipster/datasets_user_001",
                    "function": "build:real-db-upgrade_nova_mysql_user_001",
                },
            },
            'build:some_shell_job': {
                "name": "build:some_shell_job",
                "plugin": "shell_script",
                "runner_module_name": "turbo_hipster.task_plugins."
                                      "shell_script.task",
                "job_config": {
                    "name": "build:some_shell_job",
                    "shell_script": "/dev/null",
                },
            },
        }

        for job_name, job in self.worker_server.jobs.items():
            self.assertEqual(expected_jobs[job_name]['name'],
                             job['name'])
            self.assertEqual(expected_jobs[job_name]['plugin'],
                             job['plugin'])
            if 'plugin_config' in job:
                self.assertEqual(expected_jobs[job_name]['plugin_config'],
                                 job['plugin_config'])
            if 'job_config' in job:
                self.assertEqual(expected_jobs[job_name]['job_config'],
                                 job['job_config'])
            self.assertEqual(
                expected_jobs[job_name]['runner_module_name'],
                job['runner'].__module__
            )

    def test_zuul_client_started(self):
        "Test the zuul client has been started"
        self.start_server()
        self.assertFalse(self.worker_server.zuul_client.stopped())

    def test_zuul_manager_started(self):
        "Test the zuul manager has been started"
        self.start_server()
        self.assertFalse(self.worker_server.zuul_manager.stopped())


class TestZuulClient(base.TestWithGearman):
    def test_setup_gearman_worker(self):
        "Make sure the client is registered as a worker with gearman"
        pass

    def test_registered_functions(self):
        "Test the correct functions are registered with gearman"

        self.start_server()

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

        self.assertIn('build:real-db-upgrade_nova_mysql_devstack_131007',
                      self.gearman_server.functions)
        self.assertIn('build:real-db-upgrade_nova_mysql_user_001',
                      self.gearman_server.functions)
        self.assertIn('build:do_something_shelly',
                      self.gearman_server.functions)

    def test_waiting_for_job(self):
        "Make sure the client waits for jobs as expected"
        pass

    def test_stop(self):
        "Test sending a stop signal to the client exists correctly"
        pass

    def test_job_can_shutdown_th(self):
        self._load_config_fixture('shutdown-config.yaml')
        self.start_server()
        zuul = fakes.FakeZuul(self.config['zuul_server']['gearman_host'],
                              self.config['zuul_server']['gearman_port'])

        # First check we can run a job that /doesn't/ shut down turbo-hipster
        data_req = zuul.make_zuul_data()
        zuul.submit_job('build:demo_job_clean', data_req)
        zuul.wait_for_completion()
        self.assertTrue(zuul.job.complete)
        self.assertFalse(self.worker_server.stopped())

        # Now run a job that leaves the environment dirty and /should/ shut
        # down turbo-hipster
        zuul.job = None
        zuul.submit_job('build:demo_job_dirty', data_req)
        zuul.wait_for_completion()
        self.assertTrue(zuul.job.complete)
        # Give the server a second to shutdown
        time.sleep(1)
        self.assertTrue(self.worker_server.stopped())


class TestZuulManager(base.TestWithGearman):
    def test_registered_functions(self):
        "Test the correct functions are registered with gearman"

        self.start_server()

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
