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
  # $8 is an (optional) destination version number

  # Create a nova.conf file
  cat - > $2/nova-$1.conf <<EOF
[DEFAULT]
sql_connection = mysql://$4:$5@172.16.0.1/$6?charset=utf8
log_config = $7
EOF

  # Silently return git to a known good state (delete untracked files)
  git clean -xfdq

  echo "***** Start DB upgrade to state of $1 *****"
  echo "HEAD of branch under test is:"
  git log -n 1

  echo "Setting up the nova-manage entry point"
  python setup.py -q clean
  python setup.py -q develop
  python setup.py -q install

  # Log the migrations present
  echo "Migrations present:"
  ls $3/nova/db/sqlalchemy/migrate_repo/versions/*.py | sed 's/.*\///' | egrep "^[0-9]+_"

  # Flush innodb's caches
  echo "Restarting mysql"
  sudo service mysql stop
  sudo service mysql start

  echo "MySQL counters before upgrade:"
  mysql -u $4 --password=$5 $6 -e "show status like 'innodb%';"

  start_version=`mysql -u $4 --password=$5 $6 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`

  if [ "%$8%" == "%%" ]
  then
    end_version=`ls $3/nova/db/sqlalchemy/migrate_repo/versions/*.py | sed 's/.*\///' | egrep "^[0-9]+_" | tail -1 | cut -f 1 -d "_"`
  else
    end_version=$8
  fi

  echo "Test will migrate from $start_version to $end_version"
  if [ $end_version -lt $start_version ]
  then
    increment=-1
    end_version=$(( $end_version + 1 ))
  else
    increment=1
    start_version=$(( $start_version + 1))
  fi

  for i in `seq $start_version $increment $end_version`
  do
    set -x
    sudo /sbin/ip netns exec nonet `dirname $0`/nova-manage-wrapper.sh $VENV_PATH --config-file $2/nova-$1.conf --verbose db sync --version $i
    manage_exit=$?
    set +x

    echo "MySQL counters after upgrade:"
    mysql -u $4 --password=$5 $6 -e "show status like 'innodb%';"

    echo "nova-manage returned exit code $manage_exit"
    if [ $manage_exit -gt 0 ]
    then
      echo "Aborting early"
      exit $manage_exit
    fi
  done

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
  if [ $version -le "133" ]
  then
    echo "Database is from Folsom! Upgrade via Grizzly"
    git branch -D stable/grizzly || true
    git remote update
    git checkout -b stable/grizzly
    git reset --hard remotes/origin/stable/grizzly
    pip_requires
    db_sync "grizzly" $1 $2 $3 $4 $5 $6
  fi

  version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
  # Some databases are from Grizzly
  echo "Schema version is $version"
  if [ $version -le "161" ]
  then
    echo "Database is from Grizzly! Upgrade via Havana"
    git branch -D stable/havana || true
    git remote update
    git checkout -b stable/havana
    git reset --hard remotes/origin/stable/havana
    pip_requires
    db_sync "havana" $1 $2 $3 $4 $5 $6
  fi

  version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
  # Some databases are from Havana
  echo "Schema version is $version"
  if [ $version -le "216" ]
  then
    echo "Database is from Grizzly! Upgrade via Icehouse"
    git branch -D stable/icehouse || true
    git remote update
    git checkout -b stable/icehouse
    git reset --hard remotes/origin/stable/icehouse
    pip_requires
    db_sync "icehouse" $1 $2 $3 $4 $5 $6
  fi
}

echo "Test running on "`hostname`" as "`whoami`" ("`echo ~`", $HOME)"
echo "To execute this script manually, run this:"
echo "$0 $1 $2 $3 $4 $5 $6 $7 $8 $9"

# Setup the environment
export PATH=/usr/lib/ccache:$PATH
export PIP_DOWNLOAD_CACHE=$9
#export PIP_INDEX_URL="http://www.rcbops.com/pypi/mirror"
export PIP_INDEX_URL="http://pypi.openstack.org/simple/"
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
export WORKON_HOME=/var/lib/turbo-hipster/envs
VENV_PATH=$WORKON_HOME/$1
rm -rf $VENV_PATH
mkvirtualenv $1
toggleglobalsitepackages
export PYTHONPATH=$PYTHONPATH:$3

if [ ! -e $VENV_PATH ]
then
  echo "Error: making the virtual env failed"
  exit 1
fi

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

echo "Now downgrade all the way back to the last stable version (v$last_stable_version)"
db_sync "downgrade" $2 $3 $4 $5 $6 $8 $last_stable_version

# Determine the schema version
version=`mysql -u $4 --password=$5 $6 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Schema version is $version"

echo "And now back up to head from the start of trunk"
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
