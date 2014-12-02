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
import magic
import os
import requests
import select
import shutil
import subprocess
import swiftclient
import sys
import tempfile
import time


log = logging.getLogger('lib.utils')


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


def execute_to_log(cmd, logfile, timeout=-1, watch_logs=[], heartbeat=30,
                   env=None, cwd=None):
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
    logger.info("[running %s]" % cmd)
    start_time = time.time()
    p = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=cwd)

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

        if heartbeat and (time.time() - last_heartbeat > heartbeat):
            # Append to logfile
            logger.info("[heartbeat]")
            last_heartbeat = time.time()

    # Do one last write to get the remaining lines
    for fd, flag in poll_obj.poll(0):
        process(fd)

    # Clean up
    for fd, descriptor in descriptors.items():
        poll_obj.unregister(fd)
        if fd == p.stdout.fileno():
            # Don't try and close the process, it'll clean itself up
            continue
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


def zuul_swift_upload(file_path, job_arguments):
    """Upload working_dir to swift as per zuul's instructions"""
    # TODO(jhesketh): replace with swift_form_post_submit from below

    # NOTE(jhesketh): Zuul specifies an object prefix in the destination so
    #                 we don't need to be concerned with results_set_name

    file_list = []
    if os.path.isfile(file_path):
        file_list.append(file_path)
    elif os.path.isdir(file_path):
        for path, folders, files in os.walk(file_path):
            for f in files:
                f_path = os.path.join(path, f)
                file_list.append(f_path)

    # We are uploading the file_list as an HTTP POST multipart encoded.
    # First grab out the information we need to send back from the hmac_body
    payload = {}
    (object_prefix,
     payload['redirect'],
     payload['max_file_size'],
     payload['max_file_count'],
     payload['expires']) = \
        job_arguments['ZUUL_EXTRA_SWIFT_HMAC_BODY'].split('\n')

    url = job_arguments['ZUUL_EXTRA_SWIFT_URL']
    payload['signature'] = job_arguments['ZUUL_EXTRA_SWIFT_SIGNATURE']
    logserver_prefix = job_arguments['ZUUL_EXTRA_SWIFT_LOGSERVER_PREFIX']

    files = {}
    for i, f in enumerate(file_list):
        files['file%d' % (i + 1)] = open(f, 'rb')

    requests.post(url, data=payload, files=files)

    return (logserver_prefix +
            job_arguments['ZUUL_EXTRA_SWIFT_DESTINATION_PREFIX'])


def generate_log_index(file_list, logserver_prefix, results_set_name):
    """Create an index of logfiles and links to them"""

    output = '<html><head><title>Index of results</title></head><body>'
    output += '<ul>'
    for f in file_list:
        file_url = os.path.join(logserver_prefix, results_set_name, f)
        # Because file_list is simply a list to create an index for and it
        # isn't necessarily on disk we can't check if a  file is a folder or
        # not. As such we normalise the name to get the folder/filename but
        # then need to check if the last character was a trailing slash so to
        # re-append it to make it obvious that it links to a folder
        filename_postfix = '/' if f[-1] == '/' else ''
        filename = os.path.basename(os.path.normpath(f)) + filename_postfix
        output += '<li>'
        output += '<a href="%s">%s</a>' % (file_url, filename)
        output += '</li>'

    output += '</ul>'
    output += '</body></html>'
    return output


def make_index_file(file_list, logserver_prefix, results_set_name,
                    index_filename='index.html'):
    """Writes an index into a file for pushing"""

    index_content = generate_log_index(file_list, logserver_prefix,
                                       results_set_name)
    tempdir = tempfile.mkdtemp()
    fd = open(os.path.join(tempdir, index_filename), 'w')
    fd.write(index_content)
    return os.path.join(tempdir, index_filename)


def get_file_mime(file_path):
    """Get the file mime using libmagic"""

    if not os.path.isfile(file_path):
        return None

    if hasattr(magic, 'from_file'):
        return magic.from_file(file_path, mime=True)
    else:
        # no magic.from_file, we might be using the libmagic bindings
        m = magic.open(magic.MAGIC_MIME)
        m.load()
        return m.file(file_path).split(';')[0]


def swift_form_post_submit(file_list, url, hmac_body, signature):
    """Send the files to swift via the FormPost middleware"""

    # We are uploading the file_list as an HTTP POST multipart encoded.
    # First grab out the information we need to send back from the hmac_body
    payload = {}

    (object_prefix,
     payload['redirect'],
     payload['max_file_size'],
     payload['max_file_count'],
     payload['expires']) = hmac_body.split('\n')
    payload['signature'] = signature

    # Loop over the file list in chunks of max_file_count
    for sub_file_list in (file_list[pos:pos + int(payload['max_file_count'])]
                          for pos in xrange(0, len(file_list),
                                            int(payload['max_file_count']))):
        if payload['expires'] < time.time():
            raise Exception("Ran out of time uploading files!")
        files = {}
        # Zuul's log path is generated without a tailing slash. As such the
        # object prefix does not contain a slash and the files would be
        # uploaded as 'prefix' + 'filename'. Assume we want the destination
        # url to look like a folder and make sure there's a slash between.
        filename_prefix = '/' if url[-1] != '/' else ''
        for i, f in enumerate(sub_file_list):
            if os.path.getsize(f['path']) > int(payload['max_file_size']):
                sys.stderr.write('Warning: %s exceeds %d bytes. Skipping...\n'
                                 % (f['path'], int(payload['max_file_size'])))
                continue
            files['file%d' % (i + 1)] = (filename_prefix + f['filename'],
                                         open(f['path'], 'rb'),
                                         get_file_mime(f['path']))
        requests.post(url, data=payload, files=files)


def build_file_list(file_path, logserver_prefix, results_set_name,
                    create_dir_indexes=True):
    """Generate a list of files to upload to zuul. Recurses through directories
       and generates index.html files if requested."""

    # file_list: a list of dicts with {path=..., filename=...} where filename
    #            is appended to the end of the object (paths can be used)
    file_list = []
    if os.path.isfile(file_path):
        file_list.append({'filename': os.path.basename(file_path),
                          'path': file_path})
    elif os.path.isdir(file_path):
        if file_path[-1] == os.sep:
            file_path = file_path[:-1]
        parent_dir = os.path.dirname(file_path)
        for path, folders, files in os.walk(file_path):
            folder_contents = []
            for f in files:
                full_path = os.path.join(path, f)
                relative_name = os.path.relpath(full_path, parent_dir)
                push_file = {'filename': relative_name,
                             'path': full_path}
                file_list.append(push_file)
                folder_contents.append(relative_name)

            for f in folders:
                full_path = os.path.join(path, f)
                relative_name = os.path.relpath(full_path, parent_dir)
                folder_contents.append(relative_name + '/')

            if create_dir_indexes:
                index_file = make_index_file(folder_contents, logserver_prefix,
                                             results_set_name)
                relative_name = os.path.relpath(path, parent_dir)
                file_list.append({
                    'filename': os.path.join(relative_name,
                                             os.path.basename(index_file)),
                    'path': index_file})

    return file_list


def push_files(results_set_name, path_list, publish_config,
               generate_indexes=True):
    """ Push a log file/foler to a server. Returns the public URL """

    file_list = []
    root_list = []

    for file_path in path_list:
        file_path = os.path.normpath(file_path)
        if os.path.isfile(file_path):
            root_list.append(os.path.basename(file_path))
        else:
            root_list.append(os.path.basename(file_path) + '/')

        file_list += build_file_list(
            file_path, publish_config['prepend_url'], results_set_name,
            generate_indexes
        )

    index_file = ''
    if generate_indexes:
        index_file = make_index_file(root_list, publish_config['prepend_url'],
                                     results_set_name)
        file_list.append({
            'filename': os.path.basename(index_file),
            'path': index_file})

    method = publish_config['type'] + '_push_files'
    if method in globals() and hasattr(globals()[method], '__call__'):
        globals()[method](results_set_name, file_list, publish_config)

    return os.path.join(publish_config['prepend_url'], results_set_name,
                        os.path.basename(index_file))


def swift_push_files(results_set_name, file_list, swift_config):
    """ Push a log file to a swift server. """
    for file_item in file_list:
        with open(file_item['path'], 'r') as fd:
            con = swiftclient.client.Connection(
                authurl=swift_config['authurl'],
                user=swift_config['user'],
                key=swift_config['password'],
                os_options={'region_name': swift_config['region']},
                tenant_name=swift_config['tenant'],
                auth_version=2.0)
            filename = os.path.join(results_set_name, file_item['filename'])
            con.put_object(swift_config['container'], filename, fd)


def local_push_files(results_set_name, file_list, local_config):
    """ Copy the file locally somewhere sensible """
    for file_item in file_list:
        dest_dir = os.path.join(local_config['path'], results_set_name,
                                os.path.dirname(file_item['filename']))
        dest_filename = os.path.basename(file_item['filename'])
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)

        dest_file = os.path.join(dest_dir, dest_filename)
        shutil.copyfile(file_item['path'], dest_file)


def scp_push_files(results_set_name, file_path, local_config):
    """ Copy the file remotely over ssh """
    # TODO!
    pass
