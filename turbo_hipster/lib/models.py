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
import pkg_resources
import socket

from turbo_hipster.lib import common
from turbo_hipster.lib import utils


class Task(object):
    """ A base object for running a job (aka Task) """
    log = logging.getLogger("lib.models.Task")

    def __init__(self, worker_server, plugin_config, job_name):
        self.worker_server = worker_server
        self.plugin_config = plugin_config
        self.job_name = job_name
        self._reset()

        # Define the number of steps we will do to determine our progress.
        self.total_steps = 0

    def _reset(self):
        self.job = None
        self.job_arguments = None
        self.work_data = None
        self.cancelled = False
        self.success = True
        self.messages = []
        self.current_step = 0

    def start_job(self, job):
        self._reset()
        self.job = job

        if self.job is not None:
            try:
                self.job_arguments = \
                    json.loads(self.job.arguments.decode('utf-8'))
                self.log.debug("Got job from ZUUL %s" % self.job_arguments)

                # Send an initial WORK_DATA and WORK_STATUS packets
                self._send_work_data()

                # Execute the job_steps
                self.do_job_steps()

                # Finally, send updated work data and completed packets
                self._send_final_results()

            except Exception as e:
                self.log.exception('Exception handling log event.')
                if not self.cancelled:
                    self.success = False
                    self.messages.append('Exception: %s' % e)
                    self._send_work_data()
                    self.job.sendWorkException(str(e).encode('utf-8'))

    def stop_working(self, number=None):
        # Check the number is for this job instance (None will cancel all)
        # (makes it possible to run multiple workers with this task
        # on this server)
        if number is None or number == self.job.unique:
            self.log.debug("We've been asked to stop by our gearman manager")
            self.cancelled = True
            # TODO: Work out how to kill current step

    def _get_work_data(self):
        if self.work_data is None:
            hostname = os.uname()[1]
            fqdn = socket.getfqdn()
            version = pkg_resources.get_distribution('turbo_hipster').version
            self.work_data = dict(
                name=self.job_name,
                number=self.job.unique,
                manager='turbo-hipster-manager-%s' % hostname,
                url='http://localhost',
                worker_hostname=hostname,
                worker_fqdn=fqdn,
                worker_program='turbo-hipster',
                worker_version=version,
            )
        return self.work_data

    def _send_work_data(self):
        """ Send the WORK DATA in json format for job """
        self.log.debug("Send the work data response: %s" %
                       json.dumps(self._get_work_data()))
        if self.success:
            self.work_data['result'] = 'SUCCESS'
        else:
            self.work_data['result'] = '\n'.join(self.messages)
        self.job.sendWorkData(json.dumps(self._get_work_data()))

    def _send_final_results(self):
        self._send_work_data()

        if self.success:
            self.job.sendWorkComplete(
                json.dumps(self._get_work_data()))
        else:
            self.job.sendWorkFail()

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


class ShellTask(Task):
    log = logging.getLogger("lib.models.ShellTask")

    def __init__(self, worker_server, plugin_config, job_name):
        super(ShellTask, self).__init__(worker_server, plugin_config, job_name)
        # Define the number of steps we will do to determine our progress.
        self.total_steps = 6

    def _reset(self):
        super(ShellTask, self)._reset()
        self.git_path = None
        self.job_working_dir = None
        self.shell_output_log = None

    def do_job_steps(self):
        self.log.info('Step 1: Prep job working dir')
        self._prep_working_dir()

        self.log.info('Step 2: Checkout updates from git')
        self._grab_patchset(self.job_arguments)

        self.log.info('Step 3: Run shell script')
        self._execute_script()

        self.log.info('Step 4: Analyse logs for errors')
        self._parse_and_check_results()

        self.log.info('Step 5: handle the results (and upload etc)')
        self._handle_results()

        self.log.info('Step 6: Handle extra actions such as shutting down')
        self._handle_cleanup()

    @common.task_step
    def _prep_working_dir(self):
        self.job_identifier = utils.determine_job_identifier(
            self.job_arguments,
            self.plugin_config['function'],
            self.job.unique
        )
        self.job_working_dir = os.path.join(
            self.worker_server.config['jobs_working_dir'],
            self.job_identifier
        )
        self.shell_output_log = os.path.join(
            self.job_working_dir,
            'shell_output.log'
        )

        if not os.path.isdir(os.path.dirname(self.shell_output_log)):
            os.makedirs(os.path.dirname(self.shell_output_log))

    @common.task_step
    def _grab_patchset(self, job_args):
        """ Checkout the reference into config['git_working_dir'] """

        self.log.debug("Grab the patchset we want to test against")
        local_path = os.path.join(self.worker_server.config['git_working_dir'],
                                  self.job_name, job_args['ZUUL_PROJECT'])
        if not os.path.exists(local_path):
            os.makedirs(local_path)

        git_args = copy.deepcopy(job_args)

        cmd = os.path.join(os.path.join(os.path.dirname(__file__),
                                        'gerrit-git-prep.sh'))
        cmd += ' ' + self.worker_server.config['zuul_server']['gerrit_site']
        cmd += ' ' + self.worker_server.config['zuul_server']['git_origin']
        utils.execute_to_log(cmd, self.shell_output_log, env=git_args,
                             cwd=local_path)
        self.git_path = local_path
        return local_path

    @common.task_step
    def _execute_script(self):
        # Run script
        cmd = self.plugin_config['shell_script']
        cmd += (
            (' %(git_path)s %(job_working_dir)s %(unique_id)s')
            % {
                'git_path': self.git_path,
                'job_working_dir': self.job_working_dir,
                'unique_id': self.job.unique
            }
        )

        env_args = copy.deepcopy(os.environ)
        env_args.update(self.job_arguments)
        if self.job.name.startswith('build:'):
            env_args['TH_JOB_NAME'] = self.job.name[len('build:'):]
        else:
            env_args['TH_JOB_NAME'] = self.job.name

        self.script_return_code = utils.execute_to_log(
            cmd,
            self.shell_output_log,
            env=env_args
        )

    @common.task_step
    def _parse_and_check_results(self):
        if self.script_return_code > 0:
            self.success = False
            self.messages.append('Return code from test script was non-zero '
                                 '(%d)' % self.script_return_code)

    @common.task_step
    def _handle_results(self):
        """Upload the contents of the working dir either using the instructions
        provided by zuul and/or our configuration"""

        self.log.debug("Process the resulting files (upload/push)")

        if 'publish_logs' in self.worker_server.config:
            index_url = utils.push_file(
                self.job_identifier, self.shell_output_log,
                self.worker_server.config['publish_logs'])
            self.log.debug("Index URL found at %s" % index_url)
            self.work_data['url'] = index_url

        if 'ZUUL_EXTRA_SWIFT_URL' in self.job_arguments:
            # Upload to zuul's url as instructed
            utils.zuul_swift_upload(self.job_working_dir, self.job_arguments)
            self.work_data['url'] = self.job_identifier

    @common.task_step
    def _handle_cleanup(self):
        """Handle and cleanup functions. Shutdown if requested to so that no
        further jobs are ran if the environment is dirty."""
        if ('shutdown-th' in self.plugin_config and
            self.plugin_config['shutdown-th']):
            self.worker_server.shutdown_gracefully()
