#!/usr/bin/python2
#
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


import logging
import os
import threading
import yaml

import worker_manager
from os.path import join, isdir, isfile


class Server(threading.Thread):

    """ This is the worker server object to be daemonized """
    log = logging.getLogger("worker_server.Server")

    def __init__(self, config):
        super(Server, self).__init__()
        self._stop = threading.Event()
        self.config = config

        # Load extra configuration first
        # NOTE(Mattoliverau): debug_log might be specified in
        # a conf.d snippet.
        if 'conf_d' in self.config:
            self.load_extra_configuration()

        # Python logging output file.
        self.debug_log = self.config['debug_log']
        self.setup_logging(self.debug_log)

        # Config init
        self.zuul_manager = None
        self.zuul_client = None
        self.services_started = False

        # TODO: Make me unique (random?) and we should be able to run multiple
        # instances of turbo-hipster on the one host
        self.worker_name = os.uname()[1]

        self.jobs = {}
        self.load_jobs()

    def load_extra_configuration(self):
        if isdir(self.config["conf_d"]):
            extra_configs = (join(self.config["conf_d"], item)
                             for item in os.listdir(self.config["conf_d"])
                             if isfile(join(self.config["conf_d"], item)))
            for conf in extra_configs:
                try:
                    with open(conf, 'r') as config_stream:
                        extra_config = yaml.safe_load(config_stream)
                        self.config.update(extra_config)
                except:
                    self.log.warn("Failed to load extra configuration: '%s'" %
                                  (conf))
                    continue
        else:
            self.log.warn("conf_d parameter '%s' isn't a directory" %
                          (self.config["conf_d"]))

    def setup_logging(self, log_file=None):
        if log_file:
            if not os.path.isdir(os.path.dirname(log_file)):
                os.makedirs(os.path.dirname(log_file))
        logging.basicConfig(format='%(asctime)s %(name)-32s '
                            '%(levelname)-8s %(message)s',
                            filename=log_file,
                            level=logging.DEBUG)

    def load_jobs(self):
        # Legacy, load the plugins first
        self.load_plugins()

        self.log.debug("Loading jobs")
        if 'jobs' in self.config:
            for job in self.config['jobs']:
                try:
                    plugin = 'shell_script'
                    if 'plugin' in job:
                        plugin = job['plugin']

                    module = __import__('turbo_hipster.task_plugins.' +
                                        plugin + '.task',
                                        fromlist='turbo_hipster.task_plugins' +
                                        plugin)

                    self.jobs[job['name']] = {
                        'name': job['name'],
                        'plugin': plugin,
                        'job_config': job,
                        'runner': module.Runner(self, job['name'], job),
                    }
                    self.log.debug('Job %s loaded' % job['name'])
                except Exception as e:
                    self.log.exception("Failure loading job")
                    self.log.exception(e)

    def load_plugins(self):
        """ Load the available plugins from task_plugins """
        self.log.debug('Loading plugins')
        # Load plugins
        if 'plugins' in self.config:
            for plugin in self.config['plugins']:
                try:
                    module = __import__('turbo_hipster.task_plugins.' +
                                        plugin['name'] + '.task',
                                        fromlist='turbo_hipster.task_plugins' +
                                        plugin['name'])

                    self.jobs[plugin['function']] = {
                        'name': plugin['function'],
                        'plugin': plugin['name'],
                        'plugin_config': plugin,
                        'runner': module.Runner(
                            self, plugin['function'], plugin
                        ),
                    }
                    self.log.debug('Job %s loaded' % plugin['function'])
                except Exception as e:
                    self.log.exception("Failure loading plugin")
                    self.log.exception(e)

    def start_zuul_client(self):
        """ Run the tasks """
        self.log.debug('Starting zuul client')
        self.zuul_client = worker_manager.ZuulClient(self)

        for job in self.jobs.values():
            self.zuul_client.add_function(job['name'], job['runner'])

        self.zuul_client.start()

    def start_zuul_manager(self):
        self.zuul_manager = worker_manager.ZuulManager(self, self.jobs)
        self.zuul_manager.start()

    def shutdown_gracefully(self):
        """ Shutdown while no work is currently happening """
        self.log.debug('Graceful shutdown once jobs are complete...')
        thread = threading.Thread(target=self._shutdown_gracefully)
        thread.start()

    def _shutdown_gracefully(self):
        self.zuul_client.stop_gracefully()
        self.zuul_manager.stop_gracefully()
        self._stop.set()

    def shutdown(self):
        self.log.debug('Shutting down now!...')
        self.zuul_client.stop()
        self.zuul_manager.stop()
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        self.start_zuul_client()
        self.start_zuul_manager()
        self.services_started = True
        while not self.stopped():
            self._stop.wait()
