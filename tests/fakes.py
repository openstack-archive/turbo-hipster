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

import gear
import json
import time
import uuid


class FakeJob(object):
    def __init__(self):
        pass

    def sendWorkStatus(self, *args, **kwargs):
        pass


class FakeZuul(object):
    """A fake zuul/gearman client to request work from gearman and check
    results"""
    def __init__(self, server, port):
        self.gearman = gear.Client('FakeZuul')
        self.gearman.addServer(server, port)
        self.gearman.waitForServer()
        self.job = None

    def make_zuul_data(self, data={}):
        job_uuid = str(uuid.uuid1())
        defaults = {
            'ZUUL_UUID': job_uuid,
            'ZUUL_REF': 'a',
            'ZUUL_COMMIT': 'a',
            'ZUUL_PROJECT': 'a',
            'ZUUL_PIPELINE': 'a',
            'ZUUL_URL': 'http://localhost',
            'BASE_LOG_PATH': '56/123456/8',
            'LOG_PATH': '56/123456/8/check/job_name/%s' % job_uuid
        }
        defaults.update(data)
        return defaults

    def submit_job(self, name, data):
        if not self.job:
            self.job = gear.Job(name,
                                json.dumps(data),
                                unique=str(time.time()))
            self.gearman.submitJob(self.job)
        else:
            raise Exception('A job already exists in self.job')

        return self.job

    def wait_for_completion(self):
        if self.job:
            while not self.job.complete:
                time.sleep(0.1)
