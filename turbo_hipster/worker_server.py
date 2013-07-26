#!/usr/bin/python2
#
# Copyright 2013 ...


""" worker_server.py is an executable worker server that loads and runs
task_plugins. """

import argparse
import daemon
import extras
import imp
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
        # Config init
        self.config = config
        self.manager = None
        self.plugins = []
        self.load_plugins()

        # Python logging output file.
        self.debug_log = self.config['debug_log']

        self.tasks = {}

    def setup_logging(self):
        if self.debug_log:
            if not os.path.isdir(os.path.dirname(self.debug_log)):
                os.makedirs(os.path.dirname(self.debug_log))
            logging.basicConfig(format='%(asctime)s %(message)s',
                                filename=self.debug_log, level=logging.DEBUG)
        else:
            logging.basicConfig(format='%(asctime)s %(message)s',
                                level=logging.WARN)
        self.log.debug('Log pusher starting.')

    def load_plugins(self):
        """ Load the available plugins from task_plugins """
        # Load plugins
        for plugin in self.config['plugins']:
            print
            plugin_info = imp.find_module('task',
                                          [(os.path.dirname(
                                            os.path.realpath(__file__)) +
                                            '/task_plugins/' + plugin)])
            self.plugins.append(imp.load_module('task', *plugin_info))

    def run_tasks(self):
        """ Run the tasks """
        for plugin in self.plugins:
            self.tasks[plugin.__worker_name__] = plugin.Runner(self.config)
            self.tasks[plugin.__worker_name__].daemon = True
            self.tasks[plugin.__worker_name__].start()

        self.manager = worker_manager.GearmanManager(self.config, self.tasks)
        self.manager.daemon = True
        self.manager.start()

    def exit_handler(self, signum):
        signal.signal(signal.SIGUSR1, signal.SIG_IGN)
        for task_name, task in self.tasks.items():
            task.stop()
        self.manager.stop()
        sys.exit(0)

    def main(self):
        self.setup_logging()
        self.run_tasks()

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
    parser.add_argument('--background', action='store_true',
                        help='Run in the background.')
    parser.add_argument('-p', '--pidfile',
                        default='/var/run/turbo-hipster/'
                                'sql-migrate-gearman-worker.pid',
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
    main()
