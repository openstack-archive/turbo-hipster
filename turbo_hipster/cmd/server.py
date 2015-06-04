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


import argparse
import daemon
import extras
import os
import signal
import sys
import time
import yaml

from turbo_hipster import worker_server

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
PID_FILE_MODULE = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])


def setup_server(args):

    with open(args.config, 'r') as config_stream:
        config = yaml.safe_load(config_stream)

    if not config['debug_log']:
        # NOTE(mikal): debug logging _must_ be enabled for the log writing
        # in lib.utils.execute_to_log to work correctly.
        raise Exception('Debug log not configured')

    server = worker_server.Server(config)
    server.setup_logging(config['debug_log'])

    def term_handler(signum, frame):
        server.shutdown()
    signal.signal(signal.SIGTERM, term_handler)

    if args.background:
        server.daemon = True
    server.start()

    while not server.stopped():
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            print "Ctrl + C: asking tasks to exit nicely...\n"
            server.shutdown()


def main():
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config',
                        default='/etc/turbo-hipster/config.yaml',
                        help='Path to yaml config file.')
    parser.add_argument('-b', '--background', action='store_true',
                        help='Run as a daemon in the background.')
    parser.add_argument('-p', '--pidfile',
                        default='/var/run/turbo-hipster/'
                                'turbo-hipster-worker-server.pid',
                        help='PID file to lock during daemonization.')
    args = parser.parse_args()
    if args.background:
        pidfile = PID_FILE_MODULE.TimeoutPIDLockFile(args.pidfile, 10)
        with daemon.DaemonContext(pidfile=pidfile):
            setup_server(args)
    else:
        setup_server(args)


if __name__ == '__main__':
    main()
