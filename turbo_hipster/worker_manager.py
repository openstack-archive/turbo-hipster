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
import time


class ZuulManager(threading.Thread):

    """ This thread manages all of the launched gearman workers.
        As required by the zuul protocol it handles stopping builds when they
        are cancelled through stop:turbo-hipster-manager-%hostname.
        To do this it implements its own gearman worker waiting for events on
        that manager. """

    log = logging.getLogger("worker_manager.ZuulManager")

    def __init__(self, worker_server, tasks):
        super(ZuulManager, self).__init__()
        self._stop = threading.Event()
        self.stopping = False
        self.running = False

        self.worker_server = worker_server
        self.tasks = tasks

        self.gearman_worker = None
        self.setup_gearman()

    def setup_gearman(self):
        hostname = os.uname()[1]
        self.gearman_worker = gear.Worker('turbo-hipster-manager-%s'
                                          % hostname)
        self.gearman_worker.addServer(
            self.worker_server.config['zuul_server']['gearman_host'],
            self.worker_server.config['zuul_server']['gearman_port']
        )

    def register_functions(self):
        hostname = os.uname()[1]
        self.gearman_worker.registerFunction(
            'stop:turbo-hipster-manager-%s' % hostname)

    def stop_gracefully(self):
        self.stopping = True
        self.gearman_worker.stopWaitingForJobs()
        while self.running:
            self.log.debug('waiting to finish')
            time.sleep(0.1)
        self._stop.set()
        self.gearman_worker.shutdown()

    def stop(self):
        self._stop.set()
        # Unblock gearman
        self.log.debug("Telling gearman to stop waiting for jobs")
        self.gearman_worker.stopWaitingForJobs()
        self.gearman_worker.shutdown()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        while not self.stopped() and not self.stopping:
            self.running = True
            try:
                # gearman_worker.getJob() blocks until a job is available
                self.log.debug("Waiting for server")
                self.gearman_worker.waitForServer()
                if (not self.stopped() and self.gearman_worker.running and
                        self.gearman_worker.active_connections):
                    self.register_functions()
                    self.gearman_worker.waitForServer()
                    logging.debug("Waiting for job")
                    self.current_step = 0
                    job = self.gearman_worker.getJob()
                    self._handle_job(job)
            except gear.InterruptedError:
                self.log.debug('We were asked to stop waiting for jobs')
            except:
                self.log.exception('Unknown exception waiting for job.')
        self.running = False
        self.log.debug("Finished manager thread")

    def _handle_job(self, job):
        """ Handle the requested job """
        try:
            job_arguments = json.loads(job.arguments.decode('utf-8'))
            self.tasks[job_arguments['name']].stop_working(
                job_arguments['number'])
            job.sendWorkComplete()
        except Exception as e:
            self.log.exception('Exception waiting for management job.')
            job.sendWorkException(str(e).encode('utf-8'))


class ZuulClient(threading.Thread):

    """ ..."""

    log = logging.getLogger("worker_manager.ZuulClient")

    def __init__(self, worker_server):
        super(ZuulClient, self).__init__()
        self._stop = threading.Event()
        self.stopping = False
        self.running = False

        self.worker_server = worker_server

        # Set up the runner worker
        self.gearman_worker = None
        self.functions = {}

        self.job = None

        self.setup_gearman()

    def setup_gearman(self):
        self.log.debug("Set up gearman worker")
        self.gearman_worker = gear.Worker(self.worker_server.worker_name)
        self.gearman_worker.addServer(
            self.worker_server.config['zuul_server']['gearman_host'],
            self.worker_server.config['zuul_server']['gearman_port']
        )

    def register_functions(self):
        self.log.debug("Register functions with gearman")
        for function_name, plugin in self.functions.items():
            self.gearman_worker.registerFunction(function_name)
        self.log.debug(self.gearman_worker.functions)

    def add_function(self, function_name, plugin):
        self.log.debug("Add function, %s, to list" % function_name)
        self.functions[function_name] = plugin

    def stop(self):
        self._stop.set()
        for task in self.functions.values():
            task.stop_working()
        # Unblock gearman
        self.log.debug("Telling gearman to stop waiting for jobs")
        self.gearman_worker.stopWaitingForJobs()
        self.gearman_worker.shutdown()

    def stop_gracefully(self):
        self.stopping = True
        self.gearman_worker.stopWaitingForJobs()
        while self.running:
            time.sleep(0.1)
        self._stop.set()
        self.gearman_worker.shutdown()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        while not self.stopped() and not self.stopping:
            self.running = True
            try:
                # gearman_worker.getJob() blocks until a job is available
                self.log.debug("Waiting for server")
                self.gearman_worker.waitForServer()
                if (not self.stopped() and self.gearman_worker.running and
                        self.gearman_worker.active_connections):
                    self.register_functions()
                    self.gearman_worker.waitForServer()
                    self.log.debug("Waiting for job")
                    self.job = self.gearman_worker.getJob()
                    self._handle_job()
            except gear.InterruptedError:
                self.log.debug('We were asked to stop waiting for jobs')
            except:
                self.log.exception('Unknown exception waiting for job.')
        self.running = False
        self.log.debug("Finished client thread")

    def _handle_job(self):
        """ We have a job, give it to the right plugin """
        if self.job:
            self.log.debug("We have a job, we'll launch the task now.")
            self.functions[self.job.name].start_job(self.job)
