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
import numpy
import os
import sys


def main():
    for dataset in ['devstack_131007', 'devstack_150', 'trivial_500',
                    'trivial_6000', 'user_001', 'user_002']:
        process_dataset(dataset)


def process_dataset(dataset):
    with open('results.json') as f:
        results = json.loads(f.read())

    migrations = {}
    all_times = {}

    for engine in ['mysql', 'percona']:
        print
        print 'Dataset: %s' % dataset
        print 'Engine: %s' % engine
        print

        for migration in sorted(results[engine][dataset]):
            times = []
            all_times.setdefault(migration, [])
            for time in results[engine][dataset][migration]:
                for i in range(results[engine][dataset][migration][time]):
                    times.append(int(time))
                    all_times[migration].append(int(time))
                    
            times = sorted(times)
            emit_summary(engine, times, migrations, migration)

    print
    print 'Dataset: %s' % dataset
    print 'Engine: combined'
    print
    for migration in sorted(all_times.keys()):
        emit_summary('combined', all_times[migration], migrations, migration)

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
        minimum, mean, maximum, stddev = analyse(all_times[migration])
        recommend = mean + 2 * stddev
        if recommend > 30.0:
            config['maximum_migration_times'][migration] = math.ceil(recommend)

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


def analyse(times):
    np_times = numpy.array(times)
    minimum = np_times.min()
    mean = np_times.mean()
    maximum = np_times.max()
    stddev = np_times.std()
    return minimum, mean, maximum, stddev


def emit_summary(engine, times, migrations, migration):
    minimum, mean, maximum, stddev = analyse(times)
    failed_threshold = int(max(30.0, mean + stddev * 2))

    failed = 0
    for time in times:
        if time > failed_threshold:
            failed += 1

    migrations.setdefault(migration, {})
    migrations[migration][engine] = ('%.02f;%0.2f;%.02f'
                                     % (mean - 2 * stddev,
                                        mean,
                                        mean + 2 * stddev))

    if failed_threshold != 30 or failed > 0:
        print ('%s: Values range from %s to %s seconds. %d values. '
               'Mean is %.02f, stddev is %.02f.\n    '
               'Recommend max of %d. With this value %.02f%% of tests '
               'would have failed.'
               % (migration, minimum, maximum,
                  len(times), mean, stddev, failed_threshold,
                  failed * 100.0 / len(times)))


if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    main()
