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


""" worker_server.py is an executable worker server that loads and runs
task_plugins. """

import argparse
import daemon
import extras
import json
import logging
import os
import signal
import sys

import worker_manager

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
PID_FILE_MODULE = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])


class Server(object):

    """ This is the worker server object to be daemonized """
    log = logging.getLogger("worker_server.Server")

    def __init__(self, config):
        self.config = config
        # Python logging output file.
        self.debug_log = self.config['debug_log']

        # Config init
        self.zuul_manager = None
        self.zuul_client = None
        self.plugins = []

        # TODO: Make me unique (random?) and we should be able to run multiple
        # instances of turbo-hipster on the one host
        self.worker_name = os.uname()[1]

        self.tasks = {}
        self.load_plugins()

    def setup_logging(self):
        if self.debug_log:
            if not os.path.isdir(os.path.dirname(self.debug_log)):
                os.makedirs(os.path.dirname(self.debug_log))
            logging.basicConfig(format='%(asctime)s %(name)s %(message)s',
                                filename=self.debug_log, level=logging.DEBUG)
        else:
            logging.basicConfig(format='%(asctime)s %(name)s %(message)s',
                                level=logging.WARN)
        self.log.debug('Log pusher starting.')

    def load_plugins(self):
        """ Load the available plugins from task_plugins """
        self.log.debug('Loading plugins')
        # Load plugins
        for plugin in self.config['plugins']:
            self.plugins.append({
                'module': __import__('turbo_hipster.task_plugins.' +
                                     plugin['name'] + '.task',
                                     fromlist='turbo_hipster.task_plugins' +
                                     plugin['name']),
                'plugin_config': plugin
            })
            self.log.debug('Plugin %s loaded' % plugin['name'])

    def start_gearman_workers(self):
        """ Run the tasks """
        self.log.debug('Starting gearman workers')
        self.zuul_client = worker_manager.ZuulClient(self.config,
                                                     self.worker_name)

        for task_number, plugin in enumerate(self.plugins):
            module = plugin['module']
            job_name = '%s-%s-%s' % (plugin['plugin_config']['name'],
                                     self.worker_name, task_number)
            self.tasks[job_name] = module.Runner(
                self.config,
                plugin['plugin_config'],
                job_name
            )
            self.zuul_client.add_function(plugin['plugin_config']['function'],
                                          self.tasks[job_name])

        self.zuul_client.register_functions()
        self.zuul_client.daemon = True
        self.zuul_client.start()

        self.zuul_manager = worker_manager.ZuulManager(self.config, self.tasks)
        self.zuul_manager.daemon = True
        self.zuul_manager.start()

    def exit_handler(self, signum):
        self.log.debug('Exiting...')
        signal.signal(signal.SIGUSR1, signal.SIG_IGN)
        for task_name, task in self.tasks.items():
            task.stop()
        self.manager.stop()
        sys.exit(0)

    def main(self):
        self.setup_logging()
        self.start_gearman_workers()

        while True:
            try:
                signal.pause()
            except KeyboardInterrupt:
                print "Ctrl + C: asking tasks to exit nicely...\n"
                self.exit_handler(signal.SIGINT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config',
                        default=
                        '/etc/turbo-hipster/config.json',
                        help='Path to json config file.')
    parser.add_argument('-b', '--background', action='store_true',
                        help='Run as a daemon in the background.')
    parser.add_argument('-p', '--pidfile',
                        default='/var/run/turbo-hipster/'
                                'turbo-hipster-worker-server.pid',
                        help='PID file to lock during daemonization.')
    args = parser.parse_args()

    with open(args.config, 'r') as config_stream:
        config = json.load(config_stream)

    server = Server(config)

    if args.background:
        pidfile = PID_FILE_MODULE.TimeoutPIDLockFile(args.pidfile, 10)
        with daemon.DaemonContext(pidfile=pidfile):
            server.main()
    else:
        server.main()


if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    main()
