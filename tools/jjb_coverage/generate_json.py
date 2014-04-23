#!/usr/bin/python
# Copyright 2014 Rackspace Australia
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
import pprint
import sys
import xmltodict

import jenkins_jobs.builder

pp = pprint.PrettyPrinter(indent=4)


SUPPORTED = [
    'project',
    'project>builders',
    'project>builders>hudson.tasks.Shell',
    'project>builders>hudson.tasks.Shell>command'
]
IGNORED = [
    'project>description',
    'project>keepDependencies',
    'project>blockBuildWhenDownstreamBuilding',
    'project>blockBuildWhenUpstreamBuilding',
    'project>concurrentBuild',
    'project>assignedNode',
    'project>canRoam',
    'project>logRotator',
    'project>scm',
    'project>publishers',
    'project>buildWrappers'
]


class JJBCoverage(object):
    def __init__(self, jjb_config_dir):
        self.jjb = jenkins_jobs.builder.Builder('http://', '', '')
        self.jjb.load_files(jjb_config_dir)
        self.functions = {}

    def calculate_function_stats(self):
        for job in self.jjb.parser.jobs:
            instructions = xmltodict.parse(job.output())
            self._build_function_tree(job.name, instructions, self.functions)

    def _build_function_tree(self, job_name, instructions, tree, element=None):
        if element in SUPPORTED:
            tree['_support'] = 'supported'
        elif element in IGNORED:
            tree['_support'] = 'ignored'
        else:
            tree['_support'] = 'unsupported'

        if isinstance(instructions, dict):
            for key, value in instructions.items():
                if key not in tree.keys():
                    tree[key] = {}
                    tree[key]['_jobs'] = []
                if element:
                    next_element = '>'.join([element, key])
                else:
                    next_element = key

                if job_name not in tree[key]['_jobs']:
                    tree[key]['_jobs'].append(job_name)
                self._build_function_tree(job_name, value, tree[key],
                                          next_element)
        elif isinstance(instructions, list):
            if '_jobs' not in tree.keys():
                tree['_jobs'] = []
            if job_name not in tree['_jobs']:
                tree['_jobs'].append(job_name)
            for item in instructions:
                self._build_function_tree(job_name, item, tree, element)
        else:
            if instructions is not None and instructions != '':
                if '_values' not in tree:
                    tree['_values'] = {}
                if job_name not in tree['_values']:
                    tree['_values'][job_name] = []
                tree['_values'][job_name].append(instructions)

    def generate_report(self, output='public_html/jjb_report.json'):
        #self.jjb.parser.generateXML(['*turbo-hipster*'])
        self.jjb.parser.generateXML()
        self.calculate_function_stats()
        stats = {}
        stats['functions'] = self.functions
        stats['total_jobs'] = len(self.jjb.parser.jobs)

        with open(output, 'w') as outfile:
            json.dump(stats, outfile)

if __name__ == '__main__':
    coverage = JJBCoverage(sys.argv[1])
    coverage.generate_report()
