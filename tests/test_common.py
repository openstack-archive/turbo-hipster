#!/usr/bin/python2
#
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

import testtools

import fakes

from turbo_hipster.lib import common
from turbo_hipster.lib import models


class TestTaskStep(testtools.TestCase):
    def test_task_step_decorator(self):
        class FakeTask(models.Task):
            def __init__(self, global_config, plugin_config, job_name):
                super(FakeTask, self).__init__(global_config, plugin_config,
                                               job_name)
                # Define the number of steps we will do to determine our
                # progress.
                self.total_steps = 2

            @common.task_step
            def do_something(self):
                pass

            def non_step(self):
                pass

            @common.task_step
            def do_something_more(self):
                pass

        task = FakeTask({}, {}, 'job_name')
        task.job = fakes.FakeJob()

        self.assertEqual(0, task.current_step)

        task.do_something()
        self.assertEqual(1, task.current_step)

        task.non_step()
        self.assertEqual(1, task.current_step)

        task.do_something_more()
        self.assertEqual(2, task.current_step)
