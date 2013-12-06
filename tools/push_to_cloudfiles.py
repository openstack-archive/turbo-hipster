#!/usr/bin/python

import json
import os
import pyrax
import sys


def copy_dir(topdir, path, container):
    for ent in os.listdir(path):
        fullpath = os.path.join(path, ent)
        shortpath = fullpath.replace(topdir + '/', '')
        if os.path.isdir(fullpath):
            copy_dir(topdir, fullpath, container)
        else:
            print shortpath
            obj = container.upload_file(fullpath,
                                        obj_name=shortpath)

def push(topdir, region, container_name):
    pyrax.set_setting('identity_type', 'rackspace')
    with open(os.path.expanduser('~/.cloudfiles'), 'r') as f:
        conf = json.loads(f.read())
        pyrax.set_credentials(conf['access_key'],
                              conf['secret_key'],
                              region=region)
    conn = pyrax.connect_to_cloudfiles(region=region.upper(), public=False)
    container = conn.create_container(container_name)
    copy_dir(topdir, topdir, container)


if __name__ == '__main__':
    push(sys.argv[1], sys.argv[2], sys.argv[3])
