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


import copy
import json
import logging
import os
import re

from turbo_hipster.lib import utils

import turbo_hipster.task_plugins.gate_real_db_upgrade.handle_results\
    as handle_results


# Regex for log checking
MIGRATION_START_RE = re.compile('([0-9]+) -&gt; ([0-9]+)\.\.\.$')
MIGRATION_END_RE = re.compile('^done$')


class Runner(object):

    """ This thread handles the actual sql-migration tests.
        It pulls in a gearman job from the  build:gate-real-db-upgrade
        queue and runs it through _handle_patchset"""

    log = logging.getLogger("task_plugins.gate_real_db_upgrade.task.Runner")

    def __init__(self, global_config, plugin_config, job_name):
        self.global_config = global_config
        self.plugin_config = plugin_config
        self.job_name = job_name

        # Set up the runner worker
        self.datasets = []

        self.job = None
        self.job_arguments = None
        self.job_datasets = []
        self.work_data = None
        self.cancelled = False

        # Define the number of steps we will do to determine our progress.
        self.current_step = 0
        self.total_steps = 4

    def stop_worker(self, number):
        # Check the number is for this job instance
        # (makes it possible to run multiple workers with this task
        # on this server)
        if number == self.job.unique:
            self.log.debug("We've been asked to stop by our gearman manager")
            self.cancelled = True
            # TODO: Work out how to kill current step

    def start_job(self, job):
        self.job = job
        self.success = True
        self.messages = []

        if self.job is not None:
            try:
                self.job_arguments = \
                    json.loads(self.job.arguments.decode('utf-8'))
                self.log.debug("Got job from ZUUL %s" % self.job_arguments)

                # Send an initial WORK_DATA and WORK_STATUS packets
                self._send_work_data()

                # Step 1: Figure out which datasets to run
                self._do_next_step()
                self.job_datasets = self._get_job_datasets()

                # Step 2: Checkout updates from git!
                self._do_next_step()
                self.git_path = self._grab_patchset(
                    self.job_arguments,
                    self.job_datasets[0]['job_log_file_path'])

                # Step 3: Run migrations on datasets
                self._do_next_step()
                if self._execute_migrations() > 0:
                    self.success = False
                    self.messages.append('Return code from test script was '
                                         'non-zero')

                # Step 4: Analyse logs for errors
                self._do_next_step()
                self._check_all_dataset_logs_for_errors()

                # Step 5: handle the results (and upload etc)
                self._do_next_step()
                self._handle_results()

                # Finally, send updated work data and completed packets
                self._send_work_data()

                if self.work_data['result'] is 'SUCCESS':
                    self.job.sendWorkComplete(
                        json.dumps(self._get_work_data()))
                else:
                    self.job.sendWorkFail()
            except Exception as e:
                self.log.exception('Exception handling log event.')
                if not self.cancelled:
                    self.job.sendWorkException(str(e).encode('utf-8'))

    def _handle_results(self):
        """ pass over the results to handle_results.py for post-processing """
        self.log.debug("Process the resulting files (upload/push)")
        index_url = handle_results.generate_push_results(
            self.job_datasets,
            self.global_config['publish_logs']
        )
        self.log.debug("Index URL found at %s" % index_url)
        self.work_data['url'] = index_url

    def _check_all_dataset_logs_for_errors(self):
        self.log.debug('Check logs for errors')
        for i, dataset in enumerate(self.job_datasets):
            lp = handle_results.LogParser(dataset['job_log_file_path'],
                                          self.git_path)
            lp.process_log()

            if not lp.migrations:
                self.success = False
                self.messages.append('No migrations run')
            if lp.errors:
                self.success = False
                for err in lp.errors:
                    self.messages.append(err)
            if lp.warnings:
                self.success = False
                for warn in lp.warnings:
                    self.messages.append(warn)

            for migration in lp.migrations:
                if not (handle_results.check_migration(
                        migration,
                        'maximum_migration_times',
                        migration['duration'],
                        dataset['config'])):
                    self.success = False
                    self.messages.append('WARNING - Migration %s took too long'
                                         % migration[0])

            if self.success:
                self.job_datasets[i]['result'] = 'SUCCESS'
            else:
                self.job_datasets[i]['result'] = self.messages[0]

        if self.success:
            self.work_data['result'] = 'SUCCESS'
        else:
            self.work_data['result'] = '\n'.join(self.messages)

    def _get_datasets(self):
        self.log.debug("Get configured datasets to run tests against")
        if len(self.datasets) > 0:
            return self.datasets

        datasets_path = self.plugin_config['datasets_dir']
        for ent in os.listdir(datasets_path):
            dataset_dir = os.path.join(datasets_path, ent)
            if (os.path.isdir(dataset_dir) and os.path.isfile(
                    os.path.join(dataset_dir, 'config.json'))):
                dataset = {}
                with open(os.path.join(dataset_dir, 'config.json'),
                          'r') as config_stream:
                    dataset_config = json.load(config_stream)

                    dataset['name'] = ent
                    dataset['dataset_dir'] = dataset_dir
                    dataset['config'] = dataset_config

                    self.datasets.append(dataset)

        return self.datasets

    def _get_job_datasets(self):
        """ Take the applicable datasets for this job and set them up in
        self.job_datasets """

        job_datasets = []
        for dataset in self._get_datasets():
            # Only load a dataset if it is the right project and we
            # know how to process the upgrade
            if (self.job_arguments['ZUUL_PROJECT'] ==
                    dataset['config']['project'] and
                    self._get_project_command(dataset['config']['type'])):
                dataset['determined_path'] = utils.determine_job_identifier(
                    self.job_arguments, self.plugin_config['function'],
                    self.job.unique
                )
                dataset['job_log_file_path'] = os.path.join(
                    self.global_config['jobs_working_dir'],
                    dataset['determined_path'],
                    dataset['name'] + '.log'
                )
                dataset['result'] = 'UNTESTED'
                dataset['command'] = \
                    self._get_project_command(dataset['config']['type'])

                job_datasets.append(dataset)

        return job_datasets

    def _get_project_command(self, db_type):
        command = (self.job_arguments['ZUUL_PROJECT'].split('/')[-1] + '_' +
                   db_type + '_migrations.sh')
        command = os.path.join(os.path.dirname(__file__), command)
        if os.path.isfile(command):
            return command
        return False

    def _execute_migrations(self):
        """ Execute the migration on each dataset in datasets """

        self.log.debug("Run the db sync upgrade script")

        for dataset in self.job_datasets:
            cmd = os.path.join(os.path.join(os.path.dirname(__file__),
                               (self.global_config['baseline_command']
                                % self.global_config['flavor'])))
            rc = utils.execute_to_log(
                cmd,
                dataset['job_log_file_path'],
            )

            cmd = dataset['command']
            # $1 is the unique id
            # $2 is the working dir path
            # $3 is the path to the git repo path
            # $4 is the db user
            # $5 is the db password
            # $6 is the db name
            # $7 is the path to the dataset to test against
            # $8 is the logging.conf for openstack
            # $9 is the pip cache dir

            cmd += (
                (' %(unique_id)s %(job_working_dir)s %(git_path)s'
                    ' %(dbuser)s %(dbpassword)s %(db)s'
                    ' %(dataset_path)s %(logging_conf)s %(pip_cache_dir)s')
                % {
                    'unique_id': self.job.unique,
                    'job_working_dir': os.path.join(
                        self.global_config['jobs_working_dir'],
                        dataset['determined_path']
                    ),
                    'git_path': self.git_path,
                    'dbuser': dataset['config']['db_user'],
                    'dbpassword': dataset['config']['db_pass'],
                    'db': dataset['config']['database'],
                    'dataset_path': os.path.join(
                        dataset['dataset_dir'],
                        dataset['config']['seed_data']
                    ),
                    'logging_conf': os.path.join(
                        dataset['dataset_dir'],
                        dataset['config']['logging_conf']
                    ),
                    'pip_cache_dir': self.global_config['pip_download_cache']
                }
            )

            # Gather logs to watch
            syslog = '/var/log/syslog'
            sqlslo = '/var/log/mysql/slow-queries.log'
            sqlerr = '/var/log/mysql/error.log'
            if 'logs' in self.global_config:
                if 'syslog' in self.global_config['logs']:
                    syslog = self.global_config['logs']['syslog']
                if 'sqlslo' in self.global_config['logs']:
                    sqlslo = self.global_config['logs']['sqlslo']
                if 'sqlerr' in self.global_config['logs']:
                    sqlerr = self.global_config['logs']['sqlerr']

            rc = utils.execute_to_log(
                cmd,
                dataset['job_log_file_path'],
                watch_logs=[
                    ('[syslog]', syslog),
                    ('[sqlslo]', sqlslo),
                    ('[sqlerr]', sqlerr)
                ],
            )
            return rc

    def _grab_patchset(self, job_args, job_log_file_path):
        """ Checkout the reference into config['git_working_dir'] """

        self.log.debug("Grab the patchset we want to test against")
        local_path = os.path.join(self.global_config['git_working_dir'],
                                  self.job_name, job_args['ZUUL_PROJECT'])
        if not os.path.exists(local_path):
            os.makedirs(local_path)

        git_args = copy.deepcopy(job_args)
        git_args['GIT_ORIGIN'] = 'git://git.openstack.org/'

        cmd = os.path.join(os.path.join(os.path.dirname(__file__),
                                        'gerrit-git-prep.sh'))
        cmd += ' https://review.openstack.org'
        cmd += ' http://zuul.rcbops.com'
        utils.execute_to_log(cmd, job_log_file_path, env=git_args,
                             cwd=local_path)
        return local_path

    def _get_work_data(self):
        if self.work_data is None:
            hostname = os.uname()[1]
            self.work_data = dict(
                name=self.job_name,
                number=self.job.unique,
                manager='turbo-hipster-manager-%s' % hostname,
                url='http://localhost',
            )
        return self.work_data

    def _send_work_data(self):
        """ Send the WORK DATA in json format for job """
        self.log.debug("Send the work data response: %s" %
                       json.dumps(self._get_work_data()))
        self.job.sendWorkData(json.dumps(self._get_work_data()))

    def _do_next_step(self):
        """ Send a WORK_STATUS command to the gearman server.
        This can provide a progress bar. """

        # Each opportunity we should check if we need to stop
        if self.cancelled:
            self.work_data['result'] = "Failed: Job cancelled"
            self.job.sendWorkStatus(self.current_step, self.total_steps)
            self.job.sendWorkFail()
            raise Exception('Job cancelled')

        self.current_step += 1
        self.job.sendWorkStatus(self.current_step, self.total_steps)
