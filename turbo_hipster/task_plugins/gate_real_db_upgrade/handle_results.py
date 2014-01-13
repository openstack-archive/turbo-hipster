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
import tempfile
import time
import os
import re


from turbo_hipster.lib.utils import push_file


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


def generate_push_results(datasets, publish_config):
    """ Generates and pushes results """

    last_link_uri = None
    for i, dataset in enumerate(datasets):
        result_uri = push_file(dataset['determined_path'],
                               dataset['job_log_file_path'],
                               publish_config)
        datasets[i]['result_uri'] = result_uri
        last_link_uri = result_uri

    if len(datasets) > 1:
        index_file = make_index_file(datasets, 'index.html')
        # FIXME: the determined path here is just copied from the last dataset.
        # Probably should be stored elsewhere...
        index_file_url = push_file(dataset['determined_path'], index_file,
                                   publish_config)
        return index_file_url
    else:
        return last_link_uri


MIGRATION_NUMBER_RE = re.compile('^([0-9]+).*\.py$')
MIGRATION_START_RE = re.compile('.* ([0-9]+) -\> ([0-9]+)\.\.\..*$')
MIGRATION_END_RE = re.compile('done$')
MIGRATION_FINAL_SCHEMA_RE = re.compile('Final schema version is ([0-9]+)')
INNODB_STATISTIC_RE = re.compile('.* (Innodb_.*)\t([0-9]+)')


class LogParser(object):
    def __init__(self, logpath, gitpath):
        self.logpath = logpath
        self.gitpath = gitpath
        self._init()

    def _init(self):
        self.errors = []
        self.warnings = []
        self.migrations = []

    def find_schemas(self):
        """Return a list of the schema numbers present in git."""
        return [int(MIGRATION_NUMBER_RE.findall(f)[0]) for f in os.listdir(
            os.path.join(self.gitpath,
                         'nova/db/sqlalchemy/migrate_repo/versions'))
                if MIGRATION_NUMBER_RE.match(f)]

    def process_log(self):
        """Analyse a log for errors."""
        self._init()
        innodb_stats = {}
        migration_stats = {}
        current_migration = {}

        with open(self.logpath, 'r') as fd:
            migration_started = False

            for line in fd:
                if 'ERROR 1045' in line:
                    return False, "FAILURE - Could not setup seed database."
                elif 'ERROR 1049' in line:
                    return False, "FAILURE - Could not find seed database."
                elif 'ImportError' in line:
                    return False, "FAILURE - Could not import required module."
                elif MIGRATION_START_RE.search(line):
                    if current_migration:
                        current_migration['stats'] = migration_stats
                        self.migrations.append(current_migration)
                        current_migration = {}
                        migration_stats = {}

                    if migration_started:
                        # We didn't see the last one finish,
                        # something must have failed
                        self.errors.append('FAILURE - Migration started '
                                           'but did not end')

                    migration_started = True
                    current_migration['start'] = line_to_time(line)

                    m = MIGRATION_START_RE.match(line)
                    current_migration['from'] = int(m.group(1))
                    current_migration['to'] = int(m.group(2))

                elif MIGRATION_END_RE.search(line):
                    if migration_started:
                        # NOTE(mikal): we found the end to this migration
                        migration_started = False
                        current_migration['end'] = line_to_time(line)

                elif INNODB_STATISTIC_RE.search(line):
                    # NOTE(mikal): the stats for a migration step come after
                    # the migration has ended, because they're the next
                    # command in the script. We don't record them until the
                    # next migration starts (or we hit the end of the file).
                    m = INNODB_STATISTIC_RE.match(line)
                    name = m.group(1)
                    value = int(m.group(2))

                    if name in innodb_stats:
                        delta = value - innodb_stats[name]
                        if delta > 0:
                            migration_stats[name] = delta

                    innodb_stats[name] = value

                elif 'Final schema version is' in line and self.gitpath:
                    # Check the final version is as expected
                    final_version = MIGRATION_FINAL_SCHEMA_RE.findall(line)[0]
                    if int(final_version) != max(self.find_schemas()):
                        self.errors.append('FAILURE - Final schema version '
                                           'does not match expectation')

            if migration_started:
                # We never saw the end of a migration, something must have
                # failed
                self.errors.append('FAILURE - Did not find the end of a '
                                   'migration after a start')

            if current_migration:
                current_migration['stats'] = migration_stats
                self.migrations.append(current_migration)


def line_to_time(line):
    """Extract a timestamp from a log line"""
    return calendar.timegm(time.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f'))


def check_migration(migration, attribute, value, dataset_config):
    """Checks if a given migration is within its allowed parameters.

    Returns True if okay, False if it takes too long."""

    migration_number = str(migration['to'])
    allowed = dataset_config[attribute].get(
        migration_number, dataset_config[attribute]['default'])
    if value > allowed:
        return False
    return True
