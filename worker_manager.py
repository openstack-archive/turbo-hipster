# Copyright ...

import gear
import json
import logging
import os
import threading


class GearmanManager(threading.Thread):

    """ This thread manages all of the launched gearman workers.
        As required by the zuul protocol it handles stopping builds when they
        are cancelled through stop:rcbau-ci-manager-%hostname.
        To do this it implements its own gearman worker waiting for events on
        that manager. """

    log = logging.getLogger("rcbau-ci.worker_manager.Manager")

    def __init__(self, config, tasks):
        super(GearmanManager, self).__init__()
        self._stop = threading.Event()
        self.config = config
        self.tasks = tasks

        self.gearman_worker = None
        self.setup_gearman()

    def setup_gearman(self):
        hostname = os.uname()[1]
        self.gearman_worker = gear.Worker('rcbau-manager-%s'
                                          % hostname)
        self.gearman_worker.addServer(
            self.config['zuul_server']['gearman_host'],
            self.config['zuul_server']['gearman_port']
        )
        self.gearman_worker.registerFunction(
            'stop:rcbau-ci-manager-%s' % hostname)

    def stop(self):
        self._stop.set()
        # Unblock gearman
        self.log.debug("Telling gearman to stop waiting for jobs")
        self.gearman_worker.stopWaitingForJobs()
        self.gearman_worker.shutdown()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        while True and not self.stopped():
            try:
                # gearman_worker.getJob() blocks until a job is available
                logging.debug("Waiting for job")
                self.current_step = 0
                job = self.gearman_worker.getJob()
                self._handle_job(job)
            except:
                logging.exception('Exception retrieving log event.')

    def _handle_job(self, job):
        """ Handle the requested job """
        try:
            job_arguments = json.loads(job.arguments.decode('utf-8'))
            self.tasks[job_arguments['name']].stop_worker(
                job_arguments['number'])
        except Exception as e:
            self.log.exception('Exception handling log event.')
            job.sendWorkException(str(e).encode('utf-8'))
