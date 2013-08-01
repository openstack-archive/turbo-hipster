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


import gear
import json
import logging
import os
import threading

from lib import utils

__worker_name__ = 'sql-migrate-test-runner-%s' % os.uname()[1]


class Runner(threading.Thread):

    """ This thread handles the actual sql-migration tests.
        It pulls in a gearman job from the  build:gate-real-db-upgrade
        queue and runs it through _handle_patchset"""

    log = logging.getLogger("task_plugins.gate_real_db_upgrade.task.Runner")

    def __init__(self, config):
        super(Runner, self).__init__()
        self._stop = threading.Event()
        self.config = config

        # Set up the runner worker
        self.gearman_worker = None
        self.setup_gearman()

        self.datasets = []
        self.job = None
        self.work_data = None
        self.cancelled = False

        # Define the number of steps we will do to determine our progress.
        self.current_step = 0
        self.total_steps = 4

    def setup_gearman(self):
        self.gearman_worker = gear.Worker(__worker_name__)
        self.gearman_worker.addServer(
            self.config['zuul_server']['gearman_host'],
            self.config['zuul_server']['gearman_port']
        )
        self.gearman_worker.registerFunction('build:gate-real-db-upgrade')

    def stop(self):
        self._stop.set()
        # Unblock gearman
        self.log.debug("Telling gearman to stop waiting for jobs")
        self.gearman_worker.stopWaitingForJobs()
        self.gearman_worker.shutdown()

    def stopped(self):
        return self._stop.isSet()

    def stop_worker(self, number):
        self.cancelled = True

    def run(self):
        while True and not self.stopped():
            try:
                # gearman_worker.getJob() blocks until a job is available
                logging.debug("Waiting for job")
                self.current_step = 0
                self.cancelled = False
                self.job = self.gearman_worker.getJob()
                self._handle_job()
                return
            except:
                logging.exception('Exception retrieving log event.')

    def _handle_job(self):
        if self.job is not None:
            try:
                job_arguments = json.loads(self.job.arguments.decode('utf-8'))
                self.log.debug("Got job from ZUUL %s" % job_arguments)

                # Send an initial WORK_DATA and WORK_STATUS packets
                self._send_work_data()

                # Step 1: Checkout updates from git!
                self._do_next_step()
                git_path = self._grab_patchset(
                    job_arguments['ZUUL_PROJECT'],
                    job_arguments['ZUUL_REF']
                )

                # Step 2: Run migrations on datasets
                self._do_next_step()
                self._execute_migrations(git_path)

                # Step 3: Analyse logs for errors
                self._do_next_step()
                self._check_log_for_errors()

                # Step 4: handle the results (and upload etc)
                self._do_next_step()
                self._handle_results()

                # Finally, send completed packet
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

    def _get_logging_file(self, dataset):
        return os.path.join(
            self.config['job_working_dir'],
            self.job.unique,
            dataset['name'] + '.log'
        )

    def _handle_results(self):
        """ pass over the results to handle_results.py for post-processing """
        pass

    def _check_log_for_errors(self):
        # logging_file = self._get_logging_file(job)

        self.work_data['result'] = "Failed: errors found in log"

    def _get_datasets(self):
        if len(self.datasets) > 0:
            return self.datasets

        datasets_path = os.path.join(os.path.dirname(__file__),
                                     'datasets')
        for ent in os.listdir(datasets_path):
            if (os.path.isdir(os.path.join(datasets_path, ent))
               and os.path.isfile(
                    os.path.join(datasets_path, ent, 'config.json'))):
                dataset = {}
                dataset['name'] = ent
                dataset['path'] = os.path.join(datasets_path, ent)
                with open(os.path.join(dataset['path'], 'config.json'),
                            'r') as config_stream:
                    dataset['config'] = json.load(config_stream)

                self.datasets.append(dataset)

        return self.datasets

    def _execute_migrations(self, git_path):
        """ Execute the migration on each dataset in datasets """

        for dataset in self._get_datasets():

            cmd = os.path.join(os.path.dirname(__file__),
                               'nova_mysql_migrations.sh')
            # $1 is the unique id
            # $2 is the working dir path
            # $3 is the path to the git repo path
            # $4 is the nova db user
            # $5 is the nova db password
            # $6 is the nova db name
            # $7 is the path to the dataset to test against
            # $8 is the pip cache dir
            cmd += (
                (' %(unique_id)s %(working_dir)s %(git_path)s'
                    ' %(dbuser)s %(dbpassword)s %(db)s'
                    ' %(dataset_path)s %(pip_cache_dir)s')
                % {
                    'unique_id': self.job.unique,
                    'working_dir': self.config['job_working_dir'],
                    'git_path': git_path,
                    'dbuser': dataset['config']['db_user'],
                    'dbpassword': dataset['config']['db_pass'],
                    'db': dataset['config']['nova_db'],
                    'dataset_path': dataset['path'],
                    'pip_cache_dir': self.config['pip_download_cache']
                }
            )

            # Gather logs to watch
            syslog = '/var/log/syslog'
            sqlslo = '/var/log/mysql/slow-queries.log'
            sqlerr = '/var/log/mysql/error.log'
            if 'logs' in self.config:
                if 'syslog' in self.config['logs']:
                    syslog = self.config['logs']['syslog']
                if 'sqlslo' in self.config['logs']:
                    sqlslo = self.config['logs']['sqlslo']
                if 'sqlerr' in self.config['logs']:
                    sqlerr = self.config['logs']['sqlerr']

            utils.execute_to_log(
                cmd,
                self._get_logging_file(dataset),
                watch_logs=[
                    ('[syslog]', syslog),
                    ('[sqlslo]', sqlslo),
                    ('[sqlerr]', sqlerr)
                ],
            )

    def _grab_patchset(self, project_name, zuul_ref):
        """ Checkout the reference into config['git_working_dir'] """

        repo = utils.GitRepository(
            self.config['zuul_server']['git_url'] + project_name,
            os.path.join(
                self.config['git_working_dir'],
                __worker_name__,
                project_name
            )
        )

        repo.fetch(zuul_ref)
        repo.checkout('FETCH_HEAD')

        return repo.local_path

    def _get_work_data(self):
        if self.work_data is None:
            hostname = os.uname()[1]
            self.work_data = dict(
                name=__worker_name__,
                number=1,
                manager='turbo-hipster-manager-%s' % hostname,
                url='http://localhost',
            )
        return self.work_data

    def _send_work_data(self):
        """ Send the WORK DATA in json format for job """
        self.job.sendWorkData(json.dumps(self._get_work_data()))

    def _do_next_step(self):
        """ Send a WORK_STATUS command to the gearman server.
        This can provide a progress bar. """

        # Each opportunity we should check if we need to stop
        if self.stopped():
            self.work_data['result'] = "Failed: Worker interrupted/stopped"
            self.job.sendWorkStatus(self.current_step, self.total_steps)
            raise Exception('Thread stopped', 'stopping')
        elif self.cancelled:
            self.work_data['result'] = "Failed: Job cancelled"
            self.job.sendWorkStatus(self.current_step, self.total_steps)
            self.job.sendWorkFail()
            raise Exception('Job cancelled', 'stopping')

        self.current_step += 1
        self.job.sendWorkStatus(self.current_step, self.total_steps)
