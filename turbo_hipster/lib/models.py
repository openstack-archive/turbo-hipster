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

from turbo_hipster.lib import common
from turbo_hipster.lib import utils


class Task(object):

    log = logging.getLogger("lib.models.Task")

    def __init__(self, global_config, plugin_config, job_name):
        self.global_config = global_config
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
                    self.job.sendWorkException(str(e).encode('utf-8'))

    def stop_worker(self, number):
        # Check the number is for this job instance
        # (makes it possible to run multiple workers with this task
        # on this server)
        if number == self.job.unique:
            self.log.debug("We've been asked to stop by our gearman manager")
            self.cancelled = True
            # TODO: Work out how to kill current step

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

    def _send_final_results(self):
        self._send_work_data()

        if self.work_data['result'] is 'SUCCESS':
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

    def __init__(self, global_config, plugin_config, job_name):
        super(ShellTask, self).__init__(global_config, plugin_config, job_name)
        # Define the number of steps we will do to determine our progress.
        self.total_steps = 5

    def _reset(self):
        super(ShellTask, self)._reset()
        self.git_path = None
        self.job_working_dir = None
        self.shell_output_log = None

    def do_job_steps(self):
        # Step 1: Checkout updates from git
        self._grab_patchset(self.job_arguments,
                            self.job_datasets[0]['job_log_file_path'])

        # Step 2: Prep job working dir
        self._prep_working_dir()

        # Step 3: Run shell script
        self._execute_script()

        # Step 4: Analyse logs for errors
        self._parse_and_check_results()

        # Step 5: handle the results (and upload etc)
        self._handle_results()

    @common.task_step
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
        self.git_path = local_path
        return local_path

    @common.task_step
    def _prep_working_dir(self):
        self.job_working_dir = os.path.join(
            self.global_config['jobs_working_dir'],
            utils.determine_job_identifier(self.job_arguments,
                                           self.plugin_config['function'],
                                           self.job.unique)
        )
        self.shell_output_log = os.path.join(
            self.job_working_dir,
            'shell_output.log'
        )

        if not os.path.isdir(os.path.dirname(self.shell_output_log)):
            os.makedirs(os.path.dirname(self.shell_output_log))

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
        self.script_return_code = utils.execute_to_log(
            cmd,
            self.shell_output_log
        )

    @common.task_step
    def _parse_and_check_results(self):
        if self.script_return_code > 0:
            self.success = False
            self.messages.append('Return code from test script was non-zero '
                                 '(%d)' % self.script_return_code)

    @common.task_step
    def _handle_results(self):
        pass
