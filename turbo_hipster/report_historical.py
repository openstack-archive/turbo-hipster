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
import numpy
import os
import sys


def main():
    with open('results.json') as f:
        results = json.loads(f.read())

    for migration in sorted(results['mysql']['user_001']):
        times = []
        for time in results['mysql']['user_001'][migration]:
            for i in range(results['mysql']['user_001'][migration][time]):
                times.append(int(time))
        times = sorted(times)

        np_times = numpy.array(times)
        mean = np_times.mean()
        stddev = np_times.std()
        failed_threshold = int(max(30.0, mean + stddev * 2))

        failed = 0
        for time in times:
            if time > failed_threshold:
                failed += 1

        if failed_threshold != 30 or failed > 0:
            print ('%s: Values range from %s to %s seconds. %d values. '
                   'Mean is %.02f, stddev is %.02f.\n    '
                   'Recommend max of %d. With this value %.02f%% of tests '
                   'would have failed.'
                   % (migration, np_times.min(), np_times.max(), len(times),
                      mean, stddev, failed_threshold,
                      failed * 100.0 / len(times)))


if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    main()
