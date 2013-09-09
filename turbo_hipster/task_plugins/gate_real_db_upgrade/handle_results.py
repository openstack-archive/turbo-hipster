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

from turbo_hipster.lib.utils import push_file
import tempfile
import os
import re


def generate_log_index(datasets):
    """ Create an index of logfiles and links to them """
    # Loop over logfile URLs
    # Create summary and links
    output = '<html><head><title>Index of results</title></head><body>'
    output += '<ul>'
    for dataset in datasets:
        output += '<li>'
        output += '<a href="%s">%s</a>' % (dataset['result_uri'],
                                           dataset['name'])
        output += ' <span class="%s">%s</span>' % (dataset['result'],
                                                   dataset['result'])
        output += '</li>'

    output += '</ul>'
    output += '</body></html>'
    return output


def make_index_file(datasets, index_filename):
    """ Writes an index into a file for pushing """
    index_content = generate_log_index(datasets)
    tempdir = tempfile.mkdtemp()
    fd = open(os.path.join(tempdir, index_filename), 'w')
    fd.write(index_content)
    return os.path.join(tempdir, index_filename)


def generate_push_results(datasets, job_unique_number, publish_config):
    """ Generates and pushes results """

    for i, dataset in enumerate(datasets):
        result_uri = push_file(job_unique_number,
                               dataset['log_file_path'],
                               publish_config)
        datasets[i]['result_uri'] = result_uri

    index_file = make_index_file(datasets, 'index.html')
    index_file_url = push_file(job_unique_number,
                               index_file,
                               publish_config)

    return index_file_url


def check_log_for_errors(logfile, gitpath):
    """ Run regex over the given logfile to find errors

        :returns:   success (boolean), message (string)"""

    # Find the schema versions
    MIGRATION_NUMBER_RE = re.compile('^([0-9]+).*\.py$')
    schemas = [int(MIGRATION_NUMBER_RE.findall(f)[0]) for f in os.listdir(
        os.path.join(gitpath, 'nova/db/sqlalchemy/migrate_repo/versions'))
        if MIGRATION_NUMBER_RE.match(f)]

    MIGRATION_START_RE = re.compile('([0-9]+) -\> ([0-9]+)\.\.\. $')
    MIGRATION_END_RE = re.compile('done$')
    #MIGRATION_COMMAND_START = '***** Start DB upgrade to state of'
    #MIGRATION_COMMAND_END = '***** Finished DB upgrade to state of'
    MIGRATION_FINAL_SCHEMA_RE = re.compile('Final schema version is ([0-9]+)')

    with open(logfile, 'r') as fd:
        migration_started = False
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
            elif MIGRATION_END_RE.search(line):
                if migration_started:
                    # We found the end to this migration
                    migration_started = False
            elif 'Final schema version is' in line:
                # Check the final version is as expected
                final_version = MIGRATION_FINAL_SCHEMA_RE.findall(line)[0]
                if int(final_version) != max(schemas):
                    return False, "Final schema version does not match expectation"

        if migration_started:
            # We never saw the end of a migration,
            # something must have failed
            return False, ("FAILURE: Did not find the end of a migration "
                            "after a start")

    return True, "SUCCESS"
