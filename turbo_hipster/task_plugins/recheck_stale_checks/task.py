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
import logging
import os
import subprocess


class Runner(object):

    """ A simple worker which rechecks reviews with stale checks. """

    log = logging.getLogger("task_plugins.recheck_stale_checks.task.Runner")

    def __init__(self, global_config, plugin_config, job_name):
        self.global_config = global_config
        self.plugin_config = plugin_config
        self.job_name = job_name

        # Define the number of steps we will do to determine our progress.
        self.current_step = 0
        self.total_steps = 2

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
        if self.job is not None:
            try:
                self.job_arguments = \
                    json.loads(self.job.arguments.decode('utf-8'))
                self.log.debug("Got job from ZUUL %s" % self.job_arguments)

                # Send an initial WORK_DATA and WORK_STATUS packets
                self._send_work_data()

                # Step 1: Fetch information about the change
                self._do_next_step()
                out = subprocess.check_output(
                    ('ssh review.openstack.org gerrit query '
                     '--format json --current-patch-set '
                     '--all-approvals --comments %s'
                     % self.job_arguments['ZUUL_CHANGE']),
                    shell=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                gerrit = json.loads(out.split('\n')[0])

                # Step 2: Determine if this change needs a recheck
                self._do_next_step()
                patchset = gerrit['patchSets'][-1]
                patch_created = ['createdOn']

                for approval in patchset['approvals']:
                    if not approval['by']['username'] == 'jenkins':
                        continue
                    if not approval['type'] == 'VRIF':
                        continue
                    patch_verified = approval['grantedOn']

                recheck = False
                if (patch_verified - patch_created >
                    self.plugin_config['days'] * 24 * 3600):
                    recheck = True

                # Finally, send updated work data and completed packets
                self._send_work_data()
                if recheck:
                    self.job.sendWorkComplete()
                else:
                    self.job.sendWorkFail()

            except Exception as e:
                self.log.exception('Exception handling log event.')
                if not self.cancelled:
                    self.job.sendWorkException(str(e).encode('utf-8'))

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
