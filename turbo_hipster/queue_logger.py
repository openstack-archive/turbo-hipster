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


import os
import socket
import sys


def main():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('zuul.rcbops.com', 4730))
    client_socket.send('status\n')

    data = ''
    
    d = client_socket.recv(1024)
    while d:
        data += d
        if d.split('\n')[-2] == '.':
            break
        d = client_socket.recv(1024)

    queued_count = 0
    queued_detail = {}
    for line in data.split('\n')[:-2]:
        func, total, running, available_workers = line.split('\t')
        queued = int(total) - int(running)
        if queued > 0:
            queued_detail[func] = '%d (%s workers)' % (queued, available_workers)
        queued_count += queued

    print 'There are %d turbo-hipster jobs queued' % queued_count
    for job in queued_detail:
        print '    %s: %s' % (job, queued_detail[job])

    client_socket.close()

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../')))
    main()
