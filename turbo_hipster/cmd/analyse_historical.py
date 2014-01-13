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
import datetime
import json
import logging
import os
import re
import sys

import swiftclient

from turbo_hipster.task_plugins.gate_real_db_upgrade import handle_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config',
                        default=
                        '/etc/turbo-hipster/config.json',
                        help='Path to json config file.')
    args = parser.parse_args()

    with open(args.config, 'r') as config_stream:
        config = json.load(config_stream)
    swift_config = config['publish_logs']

    log = logging.getLogger(__name__)
    if not os.path.isdir(os.path.dirname(config['debug_log'])):
        os.makedirs(os.path.dirname(config['debug_log']))
    logging.basicConfig(format='%(asctime)s %(name)s %(message)s',
                        filename=config['debug_log'], level=logging.INFO)

    # Open a connection to swift
    connection = swiftclient.client.Connection(
        authurl=swift_config['authurl'],
        user=swift_config['user'],
        key=swift_config['password'],
        os_options={'region_name': swift_config['region']},
        tenant_name=swift_config['tenant'],
        auth_version=2.0)
    log.info('Got connection to swift')

    a = Analyser()

    # Iterate through the logs and determine timing information. This probably
    # should be done in a "more cloudy" way, but this is good enough for now.
    total_items = 0
    items = connection.get_container(swift_config['container'], limit=1000)[1]
    while items:
        total_items += len(items)
        print ('%s Processing %d items, %d items total'
               % (datetime.datetime.now(), len(items), total_items))

        for item in items:
            log.info('Processing %s' % item['name'])
            a.process(connection, swift_config['container'], item['name'])

        a.dump()
        items = connection.get_container(swift_config['container'],
                                         marker=item['name'], limit=1000)[1]

TEST_NAME1_RE = re.compile('.*/gate-real-db-upgrade_nova_([^_]+)_([^/]*)/.*')
TEST_NAME2_RE = re.compile('.*/gate-real-db-upgrade_nova_([^_]+)/.*/(.*).log')


class Analyser(object):
    log = logging.getLogger(__name__)

    def __init__(self):
        self.results = {}

    def dump(self):
        with open('results.json', 'w') as f:
            f.write(json.dumps(self.results, indent=4, sort_keys=True))

    def process(self, connection, container, name):
        engine_name = None
        test_name = None

        m = TEST_NAME1_RE.match(name)
        if m:
            engine_name = m.group(1)
            test_name = m.group(2)
        else:
            m = TEST_NAME2_RE.match(name)
            if m:
                engine_name = m.group(1)
                test_name = m.group(2)

        if not engine_name or not test_name:
            self.log.warn('Log name %s does not match regexp' % name)
            return

        content = connection.get_object(container, name)[1]
        with open('/tmp/logcontent', 'w') as f:
            f.write(content)

        lp = handle_results.LogParser('/tmp/logcontent', None)
        lp.process_log()
        if not lp.migrations:
            self.log.warn('Log %s contained no migrations' % name)

        for migration in lp.migrations:
            duration = migration['end'] - migration['start']
            self.results.setdefault(engine_name, {})
            self.results[engine_name].setdefault(test_name, {})
            self.results[engine_name][test_name].setdefault(migration['to'],
                                                            {})
            self.results[engine_name][test_name][migration['to']]\
                .setdefault(duration, 0)
            self.results[engine_name][test_name][migration['to']][duration] \
                += 1


if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    main()
