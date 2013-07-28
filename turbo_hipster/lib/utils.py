# Copyright ....

import git
import logging
import os
import select
import subprocess
import time


class GitRepository(object):

    """ Manage a git repository for our uses """
    log = logging.getLogger("lib.utils.GitRepository")

    def __init__(self, remote_url, local_path):
        self.remote_url = remote_url
        self.local_path = local_path
        self._ensure_cloned()

        self.repo = git.Repo(self.local_path)

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

    def _ensure_cloned(self):
        if not os.path.exists(self.local_path):
            self.log.debug("Cloning from %s to %s" % (self.remote_url,
                                                      self.local_path))
            git.Repo.clone_from(self.remote_url, self.local_path)

    """ ####UNUSED>....
    def _make_ssh_wrappesubprocessr(self, key):
        name = os.path.join(self.config['git_working_dir'], '.ssh_wrapper')
        fd = open(name, 'w')
        fd.write('#!/bin/bash\n')
        fd.write('ssh -i %s $@\n' % key)
        fd.close()
        os.chmod(name, 0755)
        os.environ['GIT_SSH'] = name

    def construct_git_url(self, project_name):
        url = 'ssh://%s@%s:%s/%s' % (
                                    self.config['gerrit_server']['user'],
                                    self.config['gerrit_server']['host'],
                                    self.config['gerrit_server']['port'],
                                    project_name
                                )
        url = 'https://%s/%s' % (
            self.config['gerrit_server']['host'],
            project_name
        )
        return url
    """


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

    logger = logging.getLogger('execute_to_log')
    log_hanlder = logging.FileHandler(logfile)
    log_formatter = logging.Formatter('%(asctime)s %(message)s')
    log_hanlder.setFormatter(log_formatter)
    logger.addHandler(log_hanlder)

    descriptors = {}

    for watch_file in watch_logs:
        fd = os.open(watch_file[1], os.O_RDONLY)
        os.lseek(fd, 0, os.SEEK_END)
        descriptors[fd] = dict(
            name=watch_file[0],
            poll=select.POLLIN,
            lines=''
        )

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

    logger.info('[script exit code = %d]' % p.returncode)
