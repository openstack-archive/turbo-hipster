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


""" Methods to handle the results of the task.

Primarily place the log files somewhere useful and optionally email
somebody """

from lib.utils import push_file


def generate_log_index(datasets):
    """ Create an index of logfiles and links to them """
    # Loop over logfile URLs
    # Create summary and links
    pass


def make_index_file(datasets):
    """ Writes an index into a file for pushing """
    generate_log_index(datasets)
    # write out to file


def generate_push_results(datasets):
    """ Generates and pushes results """

    for i, dataset in enumerate(datasets):
        files = []
        if 'publish_to' in dataset['config']:
            for publish_config in dataset['config']['publish_to']:
                files.append(push_file(dataset['name'],
                                       dataset['log_file_path'],
                                       publish_config))
        datasets[i]['files'] = files

    #index_file = make_index_file(datasets)
    #index_file_url = push_file(index_file)

    return files[0]


def check_log_for_errors(logfile):
    return True
