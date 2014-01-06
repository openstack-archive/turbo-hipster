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


import git
import logging
import os
import select
import shutil
import subprocess
import swiftclient
import time


class GitRepository(object):

    """ Manage a git repository for our uses """
    log = logging.getLogger("lib.utils.GitRepository")

    def __init__(self, remote_url, local_path):
        self.remote_url = remote_url
        self.local_path = local_path
        self._ensure_cloned()

        self.repo = git.Repo(self.local_path)

    def _ensure_cloned(self):
        if not os.path.exists(self.local_path):
            self.log.debug("Cloning from %s to %s" % (self.remote_url,
                                                      self.local_path))
            git.Repo.clone_from(self.remote_url, self.local_path)

    def fetch(self, ref):
        # The git.remote.fetch method may read in git progress info and
        # interpret it improperly causing an AssertionError. Because the
        # data was fetched properly subsequent fetches don't seem to fail.
        # So try again if an AssertionError is caught.
        origin = self.repo.remotes.origin
        self.log.debug("Fetching %s from %s" % (ref, origin))

        try:
            origin.fetch(ref)
        except AssertionError:
            origin.fetch(ref)

    def checkout(self, ref):
        self.log.debug("Checking out %s" % ref)
        return self.repo.git.checkout(ref)

    def reset(self):
        self._ensure_cloned()
        self.log.debug("Resetting repository %s" % self.local_path)
        self.update()
        origin = self.repo.remotes.origin
        for ref in origin.refs:
            if ref.remote_head == 'HEAD':
                continue
            self.repo.create_head(ref.remote_head, ref, force=True)

        # Reset to remote HEAD (usually origin/master)
        self.repo.head.reference = origin.refs['HEAD']
        self.repo.head.reset(index=True, working_tree=True)
        self.repo.git.clean('-x', '-f', '-d')

    def update(self):
        self._ensure_cloned()
        self.log.debug("Updating repository %s" % self.local_path)
        origin = self.repo.remotes.origin
        origin.update()
        # If the remote repository is repacked, the repo object's
        # cache may be out of date.  Specifically, it caches whether
        # to check the loose or packed DB for a given SHA.  Further,
        # if there was no pack or lose directory to start with, the
        # repo object may not even have a database for it.  Avoid
        # these problems by recreating the repo object.
        self.repo = git.Repo(self.local_path)


def execute_to_log(cmd, logfile, timeout=-1,
                   watch_logs=[
                       ('[syslog]', '/var/log/syslog'),
                       ('[sqlslo]', '/var/log/mysql/slow-queries.log'),
                       ('[sqlerr]', '/var/log/mysql/error.log')
                   ],
                   heartbeat=True
                   ):
    """ Executes a command and logs the STDOUT/STDERR and output of any
    supplied watch_logs from logs into a new logfile

    watch_logs is a list of tuples with (name,file) """

    if not os.path.isdir(os.path.dirname(logfile)):
        os.makedirs(os.path.dirname(logfile))

    logger = logging.getLogger(logfile)
    log_handler = logging.FileHandler(logfile)
    log_formatter = logging.Formatter('%(asctime)s %(message)s')
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    descriptors = {}

    for watch_file in watch_logs:
        if not os.path.exists(watch_file[1]):
            logger.warning('Failed to monitor log file %s: file not found'
                           % watch_file[1])
            continue

        try:
            fd = os.open(watch_file[1], os.O_RDONLY)
            os.lseek(fd, 0, os.SEEK_END)
            descriptors[fd] = {'name': watch_file[0],
                               'poll': select.POLLIN,
                               'lines': ''}
        except Exception as e:
            logger.warning('Failed to monitor log file %s: %s'
                           % (watch_file[1], e))

    cmd += ' 2>&1'
    start_time = time.time()
    p = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    descriptors[p.stdout.fileno()] = dict(
        name='[output]',
        poll=(select.POLLIN | select.POLLHUP),
        lines=''
    )

    poll_obj = select.poll()
    for fd, descriptor in descriptors.items():
        poll_obj.register(fd, descriptor['poll'])

    last_heartbeat = time.time()

    def process(fd):
        """ Write the fd to log """
        global last_heartbeat
        descriptors[fd]['lines'] += os.read(fd, 1024 * 1024)
        # Avoid partial lines by only processing input with breaks
        if descriptors[fd]['lines'].find('\n') != -1:
            elems = descriptors[fd]['lines'].split('\n')
            # Take all but the partial line
            for l in elems[:-1]:
                if len(l) > 0:
                    l = '%s %s' % (descriptors[fd]['name'], l)
                    logger.info(l)
                    last_heartbeat = time.time()
            # Place the partial line back into lines to be processed
            descriptors[fd]['lines'] = elems[-1]

    while p.poll() is None:
        if timeout > 0 and time.time() - start_time > timeout:
            # Append to logfile
            logger.info("[timeout]")
            os.kill(p.pid, 9)

        for fd, flag in poll_obj.poll(0):
            process(fd)

        if time.time() - last_heartbeat > 30:
            # Append to logfile
            logger.info("[heartbeat]")
            last_heartbeat = time.time()

    # Do one last write to get the remaining lines
    for fd, flag in poll_obj.poll(0):
        process(fd)

    # Clean up
    for fd, descriptor in descriptors.items():
        poll_obj.unregister(fd)
        os.close(fd)
    try:
        p.kill()
    except OSError:
        pass

    logger.info('[script exit code = %d]' % p.returncode)
    logger.removeHandler(log_handler)
    log_handler.flush()
    log_handler.close()
    return p.returncode


def push_file(job_log_dir, file_path, publish_config):
    """ Push a log file to a server. Returns the public URL """
    method = publish_config['type'] + '_push_file'
    if method in globals() and hasattr(globals()[method], '__call__'):
        return globals()[method](job_log_dir, file_path, publish_config)


def swift_push_file(job_log_dir, file_path, swift_config):
    """ Push a log file to a swift server. """
    with open(file_path, 'r') as fd:
        name = os.path.join(job_log_dir, os.path.basename(file_path))
        con = swiftclient.client.Connection(
            authurl=swift_config['authurl'],
            user=swift_config['user'],
            key=swift_config['password'],
            os_options={'region_name': swift_config['region']},
            tenant_name=swift_config['tenant'],
            auth_version=2.0)
        con.put_object(swift_config['container'], name, fd)
        return swift_config['prepend_url'] + name


def local_push_file(job_log_dir, file_path, local_config):
    """ Copy the file locally somewhere sensible """
    dest_dir = os.path.join(local_config['path'], job_log_dir)
    dest_filename = os.path.basename(file_path)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)

    dest_file = os.path.join(dest_dir, dest_filename)

    shutil.copyfile(file_path, dest_file)
    return local_config['prepend_url'] + os.path.join(job_log_dir,
                                                      dest_filename)


def scp_push_file(job_log_dir, file_path, local_config):
    """ Copy the file remotely over ssh """
    pass


def determine_job_identifier(zuul_arguments, job, unique):
    if 'build:' in job:
        job = job.split('build:')[1]
    return os.path.join(zuul_arguments['ZUUL_CHANGE'][:2],
                        zuul_arguments['ZUUL_CHANGE'],
                        zuul_arguments['ZUUL_PATCHSET'],
                        zuul_arguments['ZUUL_PIPELINE'],
                        job,
                        unique[:7])
