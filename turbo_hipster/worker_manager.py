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


class ZuulManager(threading.Thread):

    """ This thread manages all of the launched gearman workers.
        As required by the zuul protocol it handles stopping builds when they
        are cancelled through stop:turbo-hipster-manager-%hostname.
        To do this it implements its own gearman worker waiting for events on
        that manager. """

    log = logging.getLogger("worker_manager.GearmanManager")

    def __init__(self, config, tasks):
        super(ZuulManager, self).__init__()
        self._stop = threading.Event()
        self.config = config
        self.tasks = tasks

        self.gearman_worker = None
        self.setup_gearman()

    def setup_gearman(self):
        hostname = os.uname()[1]
        self.gearman_worker = gear.Worker('turbo-hipster-manager-%s'
                                          % hostname)
        self.gearman_worker.addServer(
            self.config['zuul_server']['gearman_host'],
            self.config['zuul_server']['gearman_port']
        )
        self.gearman_worker.registerFunction(
            'stop:turbo-hipster-manager-%s' % hostname)

    def stop(self):
        self._stop.set()
        # Unblock gearman
        self.log.debug("Telling gearman to stop waiting for jobs")
        self.gearman_worker.stopWaitingForJobs()
        self.gearman_worker.shutdown()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        while True and not self.stopped():
            try:
                # gearman_worker.getJob() blocks until a job is available
                logging.debug("Waiting for job")
                self.current_step = 0
                job = self.gearman_worker.getJob()
                self._handle_job(job)
            except:
                logging.exception('Exception retrieving log event.')

    def _handle_job(self, job):
        """ Handle the requested job """
        try:
            job_arguments = json.loads(job.arguments.decode('utf-8'))
            self.tasks[job_arguments['name']].stop_worker(
                job_arguments['number'])
            job.sendWorkComplete()
        except Exception as e:
            self.log.exception('Exception handling log event.')
            job.sendWorkException(str(e).encode('utf-8'))


class ZuulClient(threading.Thread):

    """ ..."""

    log = logging.getLogger("worker_manager.ZuulClient")

    def __init__(self, global_config, worker_name):
        super(ZuulClient, self).__init__()
        self._stop = threading.Event()
        self.global_config = global_config

        self.worker_name = worker_name

        # Set up the runner worker
        self.gearman_worker = None
        self.functions = {}

        self.job = None
        self.cancelled = False

        self.setup_gearman()

    def setup_gearman(self):
        self.log.debug("Set up gearman worker")
        self.gearman_worker = gear.Worker(self.worker_name)
        self.gearman_worker.addServer(
            self.global_config['zuul_server']['gearman_host'],
            self.global_config['zuul_server']['gearman_port']
        )
        self.register_functions()

    def register_functions(self):
        for function_name, plugin in self.functions.items():
            self.gearman_worker.registerFunction(function_name)

    def add_function(self, function_name, plugin):
        self.functions[function_name] = plugin

    def stop(self):
        self._stop.set()
        # Unblock gearman
        self.log.debug("Telling gearman to stop waiting for jobs")
        self.gearman_worker.stopWaitingForJobs()
        self.gearman_worker.shutdown()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        while True and not self.stopped():
            try:
                self.cancelled = False
                # gearman_worker.getJob() blocks until a job is available
                self.log.debug("Waiting for job")
                self.job = self.gearman_worker.getJob()
                self._handle_job()
            except:
                self.log.exception('Exception retrieving log event.')

    def _handle_job(self):
        """ We have a job, give it to the right plugin """
        self.functions[self.job.name].start_job(self.job)
