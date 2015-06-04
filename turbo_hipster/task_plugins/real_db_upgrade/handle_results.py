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


MIGRATION_NUMBER_RE = re.compile('^([0-9]+).*\.py$')
MIGRATION_START_RE = re.compile('.* ([0-9]+) -\> ([0-9]+)\.\.\..*$')
MIGRATION_END_RE = re.compile('done$')
MIGRATION_FINAL_SCHEMA_RE = re.compile('Final schema version is ([0-9]+)')
INNODB_STATISTIC_RE = re.compile('.* (Innodb_.*)\t([0-9]+)')


class LogParser(object):
    def __init__(self, logpath, gitpath):
        self.logpath = logpath
        self.gitpath = gitpath
        self._reset()

    def _reset(self):
        self.errors = []
        self.warnings = []
        self.migrations = []

    def find_schemas(self):
        """Return a list of the schema numbers present in git."""

        # TODO(mikal): once more of the cells code lands this needs to handle
        # the API migratons as well as the cells migration. Just do cells for
        # now though.
        cells_migration_path = os.path.join(
            self.gitpath,
            'nova/db/sqlalchemy/cell_migrations/migrate_repo/versions')

        if not os.path.exists(cells_migration_path):
            cells_migration_path = os.path.join(
                self.gitpath,
                'nova/db/sqlalchemy/migrate_repo/versions')

        return [int(MIGRATION_NUMBER_RE.findall(f)[0]) for f in os.listdir(
            cells_migration_path) if MIGRATION_NUMBER_RE.match(f)]

    def process_log(self):
        """Analyse a log for errors."""
        self._reset()
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
                        if (('start' in current_migration and
                             'end' in current_migration)):
                            current_migration['duration'] = (
                                current_migration['end'] -
                                current_migration['start'])
                        self.migrations.append(current_migration)
                        current_migration = {}
                        migration_stats = {}

                    if migration_started:
                        # We didn't see the last one finish,
                        # something must have failed
                        self.errors.append('FAILURE - Migration started '
                                           'but did not end')

                    migration_started = True
                    current_migration['start'] = self.line_to_time(line)

                    m = MIGRATION_START_RE.match(line)
                    current_migration['from'] = int(m.group(1))
                    current_migration['to'] = int(m.group(2))

                elif MIGRATION_END_RE.search(line):
                    if migration_started:
                        migration_started = False
                        current_migration['end'] = self.line_to_time(line)

                elif INNODB_STATISTIC_RE.search(line):
                    # NOTE(mikal): the stats for a migration step come after
                    # the migration has ended, because they're the next
                    # command in the script. We don't record them until the
                    # next migration starts (or we hit the end of the file).
                    m = INNODB_STATISTIC_RE.match(line)
                    name = m.group(1)
                    value = int(m.group(2))

                    if name in innodb_stats and name not in migration_stats:
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
                if (('start' in current_migration and
                     'end' in current_migration)):
                    current_migration['duration'] = (
                        current_migration['end'] - current_migration['start'])
                self.migrations.append(current_migration)

    def line_to_time(self, line):
        """Extract a timestamp from a log line"""
        return calendar.timegm(time.strptime(line[:23],
                                             '%Y-%m-%d %H:%M:%S,%f'))


def check_migration(migration, attribute, value, dataset_config):
    """Checks if a given migration is within its allowed parameters.

    Returns True if okay, False if it takes too long."""

    migration_name = '%s->%s' % (migration['from'], migration['to'])
    allowed = dataset_config[attribute].get(
        migration_name, dataset_config[attribute]['default'])
    if value > allowed:
        return False
    return True


def check_log_file(log_file, git_path, dataset):
    lp = LogParser(log_file, git_path)
    lp.process_log()

    success = True
    messages = []

    if not lp.migrations:
        success = False
        messages.append('No migrations run')

    if lp.errors:
        success = False
        for err in lp.errors:
            messages.append(err)

    if lp.warnings:
        success = False
        for warn in lp.warnings:
            messages.append(warn)

    for migration in lp.migrations:
        migration.setdefault('stats', {})

        # check migration completed
        if 'duration' not in migration:
            success = False
            messages.append('WARNING - Migration %s->%s failed to complete'
                            % (migration['from'], migration['to']))
            continue

        # Check total time
        if not check_migration(migration, 'maximum_migration_times',
                               migration['duration'], dataset['config']):
            success = False
            messages.append('WARNING - Migration %s->%s took too long'
                            % (migration['from'], migration['to']))

        # Check rows changed
        rows_changed = 0
        for key in ['Innodb_rows_updated',
                    'Innodb_rows_inserted',
                    'Innodb_rows_deleted']:
            rows_changed += migration['stats'].get(key, 0)

        if not check_migration(migration, 'XInnodb_rows_changed',
                               rows_changed, dataset['config']):
            success = False
            messages.append('WARNING - Migration %s->%s changed too many '
                            'rows (%d)'
                            % (migration['from'], migration['to'],
                               rows_changed))

        # Check rows read
        rows_read = migration['stats'].get('Innodb_rows_read', 0)
        if not check_migration(migration, 'Innodb_rows_read',
                               rows_read, dataset['config']):
            success = False
            messages.append('WARNING - Migration %s->%s read too many '
                            'rows (%d)'
                            % (migration['from'], migration['to'], rows_read))

    return success, messages
