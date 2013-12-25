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

from turbo_hipster.task_plugins.gate_real_db_upgrade import handle_results

TESTS_DIR = os.path.join(os.path.dirname(__file__), '../..')


class TestHandleResults(testtools.TestCase):
    def test_line_to_time(self):
        test_line = '2013-11-22 21:42:45,908 [output] 141 -> 142...  '
        result = handle_results.line_to_time(test_line)
        self.assertEqual(result, 1385156565)

    def test_migration_time_passes(self):
        with open(os.path.join(TESTS_DIR,
                               'datasets/some_dataset_example/config.json'),
                  'r') as config_stream:
            dataset_config = json.load(config_stream)

        migration_start_time = 1385116665.0
        migration_end_time = 1385116865.0

        migration_number = '151'
        result = handle_results.migration_time_passes(migration_number,
                                                      migration_start_time,
                                                      migration_end_time,
                                                      dataset_config)
        self.assertFalse(result)

        migration_number = '152'
        result = handle_results.migration_time_passes(migration_number,
                                                      migration_start_time,
                                                      migration_end_time,
                                                      dataset_config)
        self.assertTrue(result)

    def test_check_log_for_errors(self):
        logfile = os.path.join(TESTS_DIR,
                               'assets/20131007_devstack_export.log')

        def fake_find_schemas_230():
            return [230]

        lp = handle_results.LogParser(logfile, '/tmp/foo')
        lp.find_schemas = fake_find_schemas_230
        lp.process_log()
        self.assertEqual(['FAILURE - Final schema version does not match '
                         'expectation'], lp.errors)
        self.assertEqual([], lp.warnings)

        def fake_find_schemas_228():
            return [228]

        lp = handle_results.LogParser(logfile, '/tmp/foo')
        lp.find_schemas = fake_find_schemas_228
        lp.process_log()
        self.assertEqual([], lp.errors)
        self.assertEqual([], lp.warnings)

    def test_parse_log(self):
        # This is a regression test for a log which didn't used to parse.
        logfile = os.path.join(TESTS_DIR, 'assets/logcontent')
        lp = handle_results.LogParser(logfile, None)
        lp.process_log()

        self.assertEqual([], lp.errors)
        self.assertEqual([], lp.warnings)

        migrations = []
        for migration in lp.migrations:
            migrations.append(migration[0])

        for migration in range(134, 229):
            self.assertTrue(migration in migrations,
                            'Migration %d missing from %s'
                            % (migration, migrations))
