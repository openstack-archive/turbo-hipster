# Copyright 2014 Rackspace Australia
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
import logging
import os
import xmltodict

import jenkins_jobs.builder

from turbo_hipster.lib import common
from turbo_hipster.lib import models
from turbo_hipster.lib import utils


class UnimplementedJJBFunction(Exception):
    pass


class Runner(models.ShellTask):

    """A plugin to run jobs defined by JJB.
    Based on models.ShellTask the steps can be overwritten."""

    log = logging.getLogger("task_plugins.jjb_runner.task.Runner")

    def __init__(self, worker_server, plugin_config, job_name):
        super(Runner, self).__init__(worker_server, plugin_config, job_name)
        self.total_steps = 6
        self.jjb_instructions = {}
        self.script_return_codes = []

    def do_job_steps(self):
        self.log.info('Step 1: Prep job working dir')
        self._prep_working_dir()

        self.log.info('Step 2: Grab instructions from jjb')
        self._grab_jjb_instructions()

        self.log.info('Step 3: Follow JJB Instructions')
        self._execute_instructions()

        self.log.info('Step 4: Analyse logs for errors')
        self._parse_and_check_results()

        self.log.info('Step 5: handle the results (and upload etc)')
        self._handle_results()

        self.log.info('Step 6: Handle extra actions such as shutting down')
        self._handle_cleanup()

    @common.task_step
    def _grab_jjb_instructions(self):
        """ Use JJB to interpret instructions into a dictionary. """

        # For the moment we're just using xmltodict as the xml is very tightly
        # coupled to JJB. In the future we could have an interpreter for JJB
        # files.

        # Set up a builder with fake jenkins creds
        jjb = jenkins_jobs.builder.Builder('http://', '', '')
        jjb.load_files(self.plugin_config['jjb_config'])
        jjb.parser.generateXML([self.plugin_config['function']
                                .replace('build:', '')])
        if len(jjb.parser.jobs) == 1:
            # got the right job
            self.jjb_instructions = xmltodict.parse(
                jjb.parser.jobs[0].output())

    @common.task_step
    def _execute_instructions(self):
        self.log.debug(self.plugin_config['function'].replace('build:', ''))
        self.log.debug(self.jjb_instructions.keys())
        self.log.debug(self.jjb_instructions)

        # Look at all of the items in the jenkins project and raise errors
        # for unimplemented functionality
        for key, value in self.jjb_instructions['project'].items():
            self.log.debug(key)
            self.log.debug(value)

            if key in ['actions', 'properties']:
                # Not sure how to handle these when they have values
                if value is None:
                    continue
                else:
                    raise UnimplementedJJBFunction(
                        "Not sure how to handle values for %s (yet)" % key)
            elif key in ['description', 'keepDependencies',
                         'blockBuildWhenDownstreamBuilding',
                         'blockBuildWhenUpstreamBuilding', 'concurrentBuild',
                         'assignedNode', 'canRoam', 'logRotator', 'scm']:
                # Ignore all of these directives as they don't apply to
                # turbo-hipster/zuul
                continue
            elif key == 'builders':
                # Loop over builders
                self._handle_builders(value)
            elif key == 'publishers':
                # Ignore publishers for the moment
                continue
            elif key == 'buildWrappers':
                # Ignore buildWrappers for the moment but probably should
                # duplicate functionality for timeout reasons
                continue
            else:
                raise UnimplementedJJBFunction(
                    "We don't know what to do with '%s' (yet)"
                    % key)

    def _handle_builders(self, builders):
        for key, value in builders.items():
            self.log.debug('--builder')
            self.log.debug(key)
            self.log.debug(value)
            if key == 'hudson.tasks.Shell':
                self._handle_shell_items(value)
            else:
                raise UnimplementedJJBFunction(
                    "We don't know how to handle the builder '%s' (yet)"
                    % key)

    def _handle_shell_items(self, shell_tasks):
        for shell_task in shell_tasks:
            for key, value in shell_task.items():
                self.log.debug('--Shell')
                self.log.debug(key)
                self.log.debug(value)
                if key == 'command':
                    self._handle_command(value)
                else:
                    raise UnimplementedJJBFunction(
                        "We don't know how to handle the command '%s' (yet)"
                        % key)

    def _handle_command(self, command):
        # Cd to working dir
        # export job_params as env
        self.log.debug("EXECUTING COMMAND")
        cwd = os.path.join(self.job_working_dir, 'working/')
        if not os.path.isdir(os.path.dirname(cwd)):
            self.log.debug('making dir, %s' % cwd)
            os.makedirs(os.path.dirname(cwd))

        env = copy.deepcopy(self.job_arguments)
        env['PATH'] = os.environ['PATH']

        self.script_return_codes.append(utils.execute_to_log(
            command, self.shell_output_log,
            env=env,
            cwd=cwd
        ))

    @common.task_step
    def _parse_and_check_results(self):
        for return_code in self.script_return_codes:
            if return_code > 0:
                self.success = False
                self.messages.append('Return code from test script was '
                                     'non-zero (%d)' % return_code)

    @common.task_step
    def _handle_results(self):
        """Upload the contents of the working dir either using the instructions
        provided by zuul and/or our configuration"""

        self.log.debug("Process the resulting files (upload/push)")
