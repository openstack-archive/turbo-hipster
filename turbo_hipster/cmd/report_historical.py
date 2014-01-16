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


import json
import math
import MySQLdb
import os
import sys


def main():
    for dataset in ['devstack_131007', 'devstack_150', 'trivial_500',
                    'trivial_6000', 'user_001', 'user_002']:
        process_dataset(dataset)


def process_dataset(dataset):
    with open('/etc/turbo-hipster/config.json', 'r') as config_stream:
        config = json.load(config_stream)
    db = MySQLdb.connect(host=config['results']['host'],
                         port=config['results'].get('port', 3306),
                         user=config['results']['username'],
                         passwd=config['results']['password'],
                         db=config['results']['database'])
    cursor = db.cursor(MySQLdb.cursors.DictCursor)

    migrations = {}
    all_times = {}
    stats_summary = {}

    for engine in ['mysql', 'percona']:
        print '%s, %s' % (dataset, engine)
        cursor.execute('select distinct(migration) from summary where '
                       'engine="%s" and dataset="%s" order by migration;'
                       % (engine, dataset))
        migrations_list = []
        for row in cursor:
            migrations_list.append(row['migration'])

        for migration in migrations_list:
            all_times.setdefault(migration, [])

            cursor.execute('select distinct(duration), count(*) from summary '
                           'where engine="%s" and dataset="%s" and '
                           'migration="%s" group by duration;'
                           % (engine, dataset, migration))
            for row in cursor:
                for i in range(row['count(*)']):
                    all_times[migration].append(row['duration'])

            cursor.execute('select stats_json from summary where engine="%s" '
                           'and dataset="%s" and migration="%s" and '
                           'not (stats_json = "{}");'
                           % (engine, dataset, migration))
            for row in cursor:
                stats = json.loads(row['stats_json'])
                for key in stats:
                    stats_summary.setdefault(migration, {})
                    stats_summary[migration].setdefault(key, {})
                    stats_summary[migration][key].setdefault(stats[key], 0)
                    stats_summary[migration][key][stats[key]] += 1

                # Composed stats
                rows_changed = 0
                for key in ['Innodb_rows_updated',
                            'Innodb_rows_inserted',
                            'Innodb_rows_deleted']:
                    rows_changed += stats.get(key, 0)

                stats_summary[migration].setdefault('XInnodb_rows_changed', {})
                stats_summary[migration]['XInnodb_rows_changed'].setdefault(
                    rows_changed, 0)
                stats_summary[migration]['XInnodb_rows_changed'][rows_changed]\
                    += 1

    with open('results.txt', 'w') as f:
        f.write('Migration,mysql,percona\n')
        for migration in sorted(migrations.keys()):
            f.write('%s' % migration)
            for engine in ['mysql', 'percona']:
                f.write(',%s' % migrations[migration].get(engine, ''))
            f.write('\n')

    # Write out the dataset config as a json blob
    config_path = os.path.join('datasets',
                               'datasets_%s' % dataset,
                               omg_hard_to_predict_names(dataset))
    with open(os.path.join(config_path, 'input.json')) as f:
        config = json.loads(f.read())

    for migration in sorted(all_times.keys()):
        # Timing
        config_max = config['maximum_migration_times']['default']
        l = len(all_times[migration])
        if l > 10:
            sorted_all_times = sorted(all_times[migration])
            one_percent = int(math.ceil(l / 100))
            recommend = sorted_all_times[-one_percent] + 30
            if recommend > config_max:
                config['maximum_migration_times'][migration] = \
                    math.ceil(recommend)

        # Innodb stats
        if not migration in stats_summary:
            continue

        for stats_key in ['XInnodb_rows_changed', 'Innodb_rows_read']:
            config_max = config[stats_key]['default']

            values = []
            results = stats_summary[migration].get(stats_key, {})
            for result in results:
                values.append(result)

            max_value = max(values)
            rounding = max_value % 10000
            if max_value > config_max:
                config[stats_key][migration] = max_value + (10000 - rounding)

    with open(os.path.join(config_path, 'config.json'), 'w') as f:
        f.write(json.dumps(config, indent=4, sort_keys=True))


def omg_hard_to_predict_names(dataset):
    if dataset.startswith('trivial'):
        return 'nova_%s' % dataset
    if dataset == 'devstack_150':
        return 'datasets_devstack_150'
    if dataset == 'devstack_131007':
        return '131007_devstack_export'
    return dataset


if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    main()
