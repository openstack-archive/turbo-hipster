# Copyright ...

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
                job = self.gearman_worker.getJob()
                self._handle_job(job)
                return
            except:
                logging.exception('Exception retrieving log event.')

    def _handle_job(self, job):
        try:
            job_arguments = json.loads(job.arguments.decode('utf-8'))
            self.log.debug("Got job from ZUUL %s" % job_arguments)

            # Send an initial WORK_DATA and WORK_STATUS packets
            self._send_work_data(job)

            # Step 1: Checkout updates from git!
            self._do_next_step(job)

            # Checkout the patchset
            git_path = self._grab_patchset(
                job_arguments['ZUUL_PROJECT'],
                job_arguments['ZUUL_REF']
            )

            # Step 2:
            self._do_next_step(job)
            self._execute_migrations(job, git_path)

            # Step 3:
            self._do_next_step(job)

            # Final step, send completed packet
            self._send_work_data(job)
            job.sendWorkComplete(json.dumps(self._get_work_data()))
        except Exception as e:
            self.log.exception('Exception handling log event.')
            if not self.cancelled:
                job.sendWorkException(str(e).encode('utf-8'))

    def _get_datasets(self):
        datasets_path = os.path.join(os.path.dirname(__file__),
                                     'datasets')

        datasets = []

        for ent in os.listdir(datasets_path):
            if (os.path.isdir(os.path.join(datasets_path, ent))
               and os.path.isfile(
                    os.path.join(datasets_path, ent, 'config.json'))):
                datasets.append(
                    os.path.join(datasets_path, ent))

        return datasets

    def _execute_migrations(self, job, git_path):
        """ Execute the migration on each dataset in datasets """

        for dataset_path in self._get_datasets():
            with open(os.path.join(dataset_path, 'config.json'),
                      'r') as config_stream:
                dataset_config = json.load(config_stream)

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
                ('%(unique_id)s %(working_dir)s %(git_path)s'
                    ' %(dbuser)s %(dbpassword)s %(db)s'
                    ' %(dataset_path)s %(pip_cache_dir)s')
                % {
                    'unique_id': job.unique,
                    'working_dir': self.config['job_working_dir'],
                    'git_path': git_path,
                    'dbuser': dataset_config['db_user'],
                    'dbpassword': dataset_config['db_pass'],
                    'db': dataset_config['nova_db'],
                    'dataset_path': dataset_path,
                    'pip_cache_dir': self.config['pip_download_cache']
                }
            )

            print cmd
            """utils.execute_to_log(
                                    cmd,
                                    os.path.join(
                                        self.config['job_working_dir'],
                                        job.unique,
                                        'testing.log'
                                    )
                                )"""

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

    def _send_work_data(self, job):
        """ Send the WORK DATA in json format for job """
        job.sendWorkData(json.dumps(self._get_work_data()))

    def _do_next_step(self, job):
        """ Send a WORK_STATUS command to the gearman server.
        This can provide a progress bar. """

        # Each opportunity we should check if we need to stop
        if self.stopped():
            self.work_data['result'] = "Failed: Worker interrupted/stopped"
            job.sendWorkStatus(self.current_step, self.total_steps)
            raise Exception('Thread stopped', 'stopping')
        elif self.cancelled:
            self.work_data['result'] = "Failed: Job cancelled"
            job.sendWorkStatus(self.current_step, self.total_steps)
            job.sendWorkFail()
            raise Exception('Job cancelled', 'stopping')

        self.current_step += 1
        job.sendWorkStatus(self.current_step, self.total_steps)
