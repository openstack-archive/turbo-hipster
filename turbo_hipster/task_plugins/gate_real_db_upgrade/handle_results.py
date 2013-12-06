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


""" Methods to handle the results of the task.

Primarily place the log files somewhere useful and optionally email
somebody """

import calendar
import time
import os
import re


from turbo_hipster.lib.utils import push_file


def generate_push_results(datasets, publish_config):
    """ Generates and pushes results """

    # NOTE(mikal): because of the way we run the tests in parallel, there is
    # only ever one dataset per push.
    link_uri = None
    for i, dataset in enumerate(datasets):
        result_uri = push_file(dataset['determined_path'],
                               dataset['job_log_file_path'],
                               publish_config)
        datasets[i]['result_uri'] = result_uri
        link_uri = result_uri

    return link_uri


def find_schemas(gitpath):
    MIGRATION_NUMBER_RE = re.compile('^([0-9]+).*\.py$')
    return [int(MIGRATION_NUMBER_RE.findall(f)[0]) for f in os.listdir(
            os.path.join(gitpath, 'nova/db/sqlalchemy/migrate_repo/versions'))
            if MIGRATION_NUMBER_RE.match(f)]


def check_log_for_errors(logfile, gitpath, dataset_config):
    """ Run regex over the given logfile to find errors

        :returns:   success (boolean), message (string)"""

    MIGRATION_START_RE = re.compile('([0-9]+) -\> ([0-9]+)\.\.\. $')
    MIGRATION_END_RE = re.compile('done$')
    #MIGRATION_COMMAND_START = '***** Start DB upgrade to state of'
    #MIGRATION_COMMAND_END = '***** Finished DB upgrade to state of'
    MIGRATION_FINAL_SCHEMA_RE = re.compile('Final schema version is ([0-9]+)')

    with open(logfile, 'r') as fd:
        migration_started = False
        warnings = []
        for line in fd:
            if 'ERROR 1045' in line:
                return False, "FAILURE: Could not setup seed database."
            elif 'ERROR 1049' in line:
                return False, "FAILURE: Could not find seed database."
            elif 'ImportError' in line:
                return False, "FAILURE: Could not import required module."
            elif MIGRATION_START_RE.search(line):
                if migration_started:
                    # We didn't see the last one finish,
                    # something must have failed
                    return False, ("FAILURE: Did not find the end of a "
                                   "migration after a start")

                migration_started = True
                migration_start_time = line_to_time(line)
                migration_number_from = MIGRATION_START_RE.findall(line)[0][0]
                migration_number_to = MIGRATION_START_RE.findall(line)[0][1]
            elif MIGRATION_END_RE.search(line):
                if migration_started:
                    # We found the end to this migration
                    migration_started = False
                    if migration_number_to > migration_number_from:
                        migration_end_time = line_to_time(line)
                        if not migration_time_passes(migration_number_to,
                                                     migration_start_time,
                                                     migration_end_time,
                                                     dataset_config):
                            warnings.append("WARNING: Migration %s took too "
                                            "long" % migration_number_to)
            elif 'Final schema version is' in line:
                # Check the final version is as expected
                final_version = MIGRATION_FINAL_SCHEMA_RE.findall(line)[0]
                if int(final_version) != max(find_schemas(gitpath)):
                    return False, ("Final schema version does not match "
                                   "expectation")

        if migration_started:
            # We never saw the end of a migration,
            # something must have failed
            return False, ("FAILURE: Did not find the end of a migration "
                           "after a start")
        elif len(warnings) > 0:
            return False, ', '.join(warnings)

    return True, "SUCCESS"


def line_to_time(line):
    """Extract a timestamp from a log line"""
    return calendar.timegm(time.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f'))


def migration_time_passes(migration_number, migration_start_time,
                          migration_end_time, dataset_config):
    """Determines if the difference between the migration_start_time and
    migration_end_time is acceptable.

    The dataset configuration should specify a default maximum time and any
    migration specific times in the maximum_migration_times dictionary.

    Returns True if okay, False if it takes too long."""

    if migration_number in dataset_config['maximum_migration_times']:
        allowed_time = \
            dataset_config['maximum_migration_times'][migration_number]
    else:
        allowed_time = dataset_config['maximum_migration_times']['default']

    if (migration_end_time - migration_start_time) > allowed_time:
        return False

    return True
