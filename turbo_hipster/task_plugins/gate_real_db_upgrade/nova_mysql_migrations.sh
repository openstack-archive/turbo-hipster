#!/bin/bash
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


# $1 is the unique id
# $2 is the working dir path
# $3 is the path to the git repo path
# $4 is the nova db user
# $5 is the nova db password
# $6 is the nova db name
# $7 is the path to the dataset to test against
# $8 is the logging.conf for openstack
# $9 is the pip cache dir

# We also support the following environment variables to tweak our behavour:
#   NOCLEANUP: if set to anything, don't cleanup at the end of the run

pip_requires() {
  pip install -q mysql-python
  pip install -q eventlet
  requires="tools/pip-requires"
  if [ ! -e $requires ]
  then
    requires="requirements.txt"
  fi
  echo "Install pip requirements from $requires"
  pip install -q -r $requires
  echo "Requirements installed"
}

db_sync() {
  # $1 is the test target
  # $2 is the working dir path
  # $3 is the path to the git repo path
  # $4 is the nova db user
  # $5 is the nova db password
  # $6 is the nova db name
  # $7 is the logging.conf for openstack
  # $8 is any sync options

  # Create a nova.conf file
  cat - > $2/nova-$1.conf <<EOF
[DEFAULT]
sql_connection = mysql://$4:$5@172.16.0.1/$6?charset=utf8
log_config = $7
EOF

  find $3 -type f -name "*.pyc" -exec rm -f {} \;
  echo "***** Start DB upgrade to state of $1 *****"
  echo "Setting up the nova-manage entry point"
  python setup.py -q clean
  python setup.py -q develop
  python setup.py -q install
  set -x
  sudo /sbin/ip netns exec nonet `dirname $0`/nova-manage-wrapper $VENV_PATH --config-file $2/nova-$1.conf --verbose db sync $8
  manage_exit=$?
  set +x

  echo "nova-manage returned exit code $manage_exit"
  if [ $manage_exit -gt 0 ]
  then
    echo "Aborting early"
    exit $manage_exit
  fi


  echo "***** Finished DB upgrade to state of $1 *****"
}

stable_release_db_sync() {
  # $1 is the working dir path
  # $2 is the path to the git repo path
  # $3 is the nova db user
  # $4 is the nova db password
  # $5 is the nova db name
  # $6 is the logging.conf for openstack

  version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`

  # Some databases are from Folsom
  echo "Schema version is $version"
  if [ $version == "133" ] # I think this should be [ $version lt "133" ]
  then
    echo "Database is from Folsom! Upgrade via Grizzly"
    git checkout stable/grizzly
    pip_requires
    db_sync "grizzly" $1 $2 $3 $4 $5 $6
  fi

  version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
  # Some databases are from Grizzly
  echo "Schema version is $version"
  if [ $version == "161" ] # I think this should be [ $version lt "161" ]
  then
    echo "Database is from Grizzly! Upgrade via Havana"
    git checkout stable/havana
    pip_requires
    db_sync "havana" $1 $2 $3 $4 $5 $6
  fi
}

echo "Test running on "`hostname`" as "`whoami`" ("`echo ~`", $HOME)"
echo "To execute this script manually, run this:"
echo "$0 $1 $2 $3 $4 $5 $6 $7 $8 $9"

# Setup the environment
export PATH=/usr/lib/ccache:$PATH
export PIP_DOWNLOAD_CACHE=$9
export PIP_INDEX_URL="http://www.rcbops.com/pypi/mirror"
export PIP_EXTRA_INDEX_URL="https://pypi.python.org/simple/"

# Restore database to known good state
echo "Restoring test database $6"
set -x
mysql -u $4 --password=$5 -e "drop database $6"
mysql -u $4 --password=$5 -e "create database $6"
mysql -u $4 --password=$5 $6 < $7
set +x

echo "Build test environment"
cd $3

echo "Setting up virtual env"
source ~/.bashrc
source /etc/bash_completion.d/virtualenvwrapper
VENV_PATH=~/.virtualenvs/$1
rm -rf $VENV_PATH
mkvirtualenv $1
toggleglobalsitepackages
export PYTHONPATH=$PYTHONPATH:$3

# zuul puts us in a headless mode, lets check it out into a working branch
git branch -D working 2> /dev/null
git checkout -b working

stable_release_db_sync $2 $3 $4 $5 $6 $8

last_stable_version=`mysql -u $4 --password=$5 $6 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Schema after stable_release_db_sync version is $last_stable_version"

# Make sure the test DB is up to date with trunk
if [ `git show | grep "^\-\-\-" | grep "migrate_repo/versions" | wc -l` -gt 0 ]
then
  echo "This change alters an existing migration, skipping trunk updates."
else
  echo "Update database to current state of trunk"
  git checkout master
  pip_requires
  db_sync "trunk" $2 $3 $4 $5 $6 $8
  git checkout working
fi

# Now run the patchset
echo "Now test the patchset"
pip_requires
db_sync "patchset" $2 $3 $4 $5 $6 $8

# Determine the schema version
version=`mysql -u $4 --password=$5 $6 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Schema version is $version"

#target_version=`ls $3/nova/db/sqlalchemy/migrate_repo/versions | head -1 | cut -f 1 -d "_"`
echo "Now downgrade all the way back to the last stable version (v$last_stable_version)"
db_sync "patchset" $2 $3 $4 $5 $6 $8 "--version $last_stable_version"

# Determine the schema version
version=`mysql -u $4 --password=$5 $6 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Schema version is $version"

echo "And now back up to head from the start of trunk"
git checkout working  # I think this line is redundant
db_sync "patchset" $2 $3 $4 $5 $6 $8

# Determine the final schema version
version=`mysql -u $4 --password=$5 $6 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Final schema version is $version"

if [ "%$NOCLEANUP%" == "%%" ]
then
  # Cleanup virtual env
  echo "Cleaning up virtual env"
  deactivate
  rmvirtualenv $1
fi
