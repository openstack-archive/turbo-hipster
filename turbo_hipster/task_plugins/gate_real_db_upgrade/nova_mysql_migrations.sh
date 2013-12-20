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

# We also support the following environment variables to tweak our behavour:
#   NOCLEANUP: if set to anything, don't cleanup at the end of the run

# $1 is the unique id
# $2 is the working dir path
# $3 is the path to the git repo path
# $4 is the nova db user
# $DB_PASS is the nova db password
# $6 is the nova db name
# $7 is the path to the dataset to test against
# $8 is the logging.conf for openstack
# $9 is the pip cache dir

UNIQUE_ID=$1
WORKING_PATH=$2
GIT_REPO_PATH=$3
DB_USER=$4
DB_PASS=$5
DATABASE=$6
DATASET_SEED=$7
LOGGING=$8
PIP_DOWNLOAD_CACHE=$9

CONTAINER_NAME="th_working_container_$UNIQUE_ID"

STARTING_CONTAINER_NAME="th_container_bare"
LXCPATH="/var/lib/lxc"
CONTAINER_ROOT="$LXCPATH/$CONTAINER_NAME/rootfs"
CONTAINER_DISTRO_TYPE="ubuntu"
CONTAINER_PACKAGES="mysql-server python-virtualenv mysql-client python-setuptools python-pip libxml2-dev libxml2-utils libxslt-dev libmysqlclient-dev pep8 postgresql-server-dev-9.1 python2.7-dev python-coverage python-netaddr python-mysqldb python-git virtualenvwrapper python-numpy"

CONTAINER_WORKING_PATH="$CONTAINER_ROOT$WORKING_PATH"
CONTAINER_GIT_REPO_PATH="$CONTAINER_ROOT$GIT_REPO_PATH"

VIRTUALENV="/tmp/virtualenv/$UNIQUE_ID"
CONTAINER_VIRTUALENV="$CONTAINER_ROOT$VIRTUALENV"

pip_requires() {
  source $CONTAINER_VIRTUALENV/bin/activate
  pip install --download-cache $PIP_DOWNLOAD_CACHE -q mysql-python
  pip install --download-cache $PIP_DOWNLOAD_CACHE -q eventlet
  requires="$CONTAINER_GIT_REPO_PATH/tools/pip-requires"
  if [ ! -e $requires ]
  then
    requires="$CONTAINER_GIT_REPO_PATH/requirements.txt"
  fi
  echo "Install pip requirements from $requires"
  pip install --download-cache $PIP_DOWNLOAD_CACHE -q -r $requires
  echo "Requirements installed"
  deactivate
  virtualenv --relocatable $CONTAINER_VIRTUALENV
}

get_db_version() {
  VERSION=`sudo lxc-attach -n $CONTAINER_NAME -- mysql -u $DB_USER --password=$DB_PASS $DATABASE -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
}

db_sync() {
  # $1 is the test target
  # $2 is any sync options

  # Create a nova.conf file
  cat - > $CONTAINER_WORKING_PATH/nova-$1.conf <<EOF
[DEFAULT]
sql_connection = mysql://$DB_USER:$DB_PASS@localhost/$DATABASE?charset=utf8
log_config = $LOGGING
EOF

  find $CONTAINER_GIT_REPO_PATH -type f -name "*.pyc" -exec rm -f {} \;
  echo "***** Start DB upgrade to state of $1 *****"
  nova_manage="$GIT_REPO_PATH/nova/bin/nova-manage"
  if [ -e $nova_manage ]
  then
    echo "Running nova-manage that pre-dates entry points"
    cat - > $CONTAINER_ROOT/tmp/run.sh <<EOF
source $VIRTUALENV/bin/activate
python $nova_manage --config-file $WORKING_PATH/nova-$1.conf --verbose db sync $2
deactivate
virtualenv --relocatable $VIRTUALENV
EOF
    set -x
    sudo lxc-attach -n $CONTAINER_NAME -- bash /tmp/run.sh
  else
    echo "No such file: $nova_manage"
    echo "Setting up the nova-manage entry point"
    cat - > $CONTAINER_ROOT/tmp/run.sh <<EOF
source $VIRTUALENV/bin/activate
python $GIT_REPO_PATH/setup.py -q clean
python $GIT_REPO_PATH/setup.py -q develop
python $GIT_REPO_PATH/setup.py -q install
nova-manage --config-file $WORKING_PATH/nova-$1.conf --verbose db sync $2
deactivate
virtualenv --relocatable $VIRTUALENV
EOF
    set -x
    sudo lxc-attach -n $CONTAINER_NAME -- bash /tmp/run.sh
  fi
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
  get_db_version
  # Some databases are from Folsom
  echo "Schema version is $VERSION"
  if [ $VERSION == "133" ] # I think this should be [ $VERSION lt "133" ]
  then
    echo "Database is from Folsom! Upgrade via Grizzly"
    git checkout stable/grizzly
    pip_requires
    db_sync "grizzly"
  fi

  get_db_version
  # Some databases are from Grizzly
  echo "Schema version is $VERSION"
  if [ $VERSION == "161" ] # I think this should be [ $VERSION lt "161" ]
  then
    echo "Database is from Grizzly! Upgrade via Havana"
    git checkout stable/havana
    pip_requires
    db_sync "havana"
  fi
}

echo "Test running on "`hostname`
echo "To execute this script manually, run this:"
echo "$0 $1 $2 $3 $4 $5 $6 $7 $8 $9"
set -x

# Set up the contain to run nova inside
if [[ ! $(sudo lxc-ls) =~ $STARTING_CONTAINER_NAME ]]
then
  sudo lxc-create -n $STARTING_CONTAINER_NAME -t $CONTAINER_DISTRO_TYPE
  sudo lxc-start -n $STARTING_CONTAINER_NAME -d
  sudo lxc-attach -n $STARTING_CONTAINER_NAME -- debconf-set-selections <<< 'mysql-server mysql-server/root_password password root'
  sudo lxc-attach -n $STARTING_CONTAINER_NAME -- debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password root'
  sudo lxc-attach -n $STARTING_CONTAINER_NAME -- apt-get update -y
  sudo lxc-attach -n $STARTING_CONTAINER_NAME -- apt-get upgrade -y
  sudo lxc-attach -n $STARTING_CONTAINER_NAME -- apt-get install -y $CONTAINER_PACKAGES
  sudo lxc-stop -n $STARTING_CONTAINER_NAME
fi
sudo lxc-clone -o $STARTING_CONTAINER_NAME -n $CONTAINER_NAME
# TODO: Remove networking here
sudo lxc-start -n $CONTAINER_NAME -d
# Wait for MySQLd to start
while ! nc -vz localhost 3306; do sleep 1; done
# apparently even with checking the port we need to wait a bit more, so we'll sleep arbitrarily
sleep 15
sudo lxc-attach -n $CONTAINER_NAME -- mysql -u root --password=root -e "CREATE USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
sudo lxc-attach -n $CONTAINER_NAME -- mysql -u root --password=root -e "GRANT ALL ON *.* TO '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS' WITH GRANT OPTION;"
sudo lxc-attach -n $CONTAINER_NAME -- mysql -u root --password=root -e "FLUSH PRIVILEGES;"

# Copy the working dir and git dir into the container

sudo lxc-attach -n $CONTAINER_NAME -- mkdir -p `dirname $WORKING_PATH`
sudo lxc-attach -n $CONTAINER_NAME -- mkdir -p `dirname $GIT_REPO_PATH`
sudo lxc-attach -n $CONTAINER_NAME -- mkdir -p $VIRTUALENV
sudo lxc-attach -n $CONTAINER_NAME -- chmod -R 777 /var/lib/turbo-hipster
sudo lxc-attach -n $CONTAINER_NAME -- chmod -R 777 $VIRTUALENV
cp -R $WORKING_PATH $CONTAINER_WORKING_PATH
cp -R $GIT_REPO_PATH $CONTAINER_GIT_REPO_PATH
set +x

# Setup the environment
export PATH=/usr/lib/ccache:$PATH
export PIP_DOWNLOAD_CACHE=$PIP_DOWNLOAD_CACHE
virtualenv --system-site-packages $CONTAINER_VIRTUALENV
virtualenv --relocatable $CONTAINER_VIRTUALENV

# Restore database to known good state
echo "Restoring test database $DATABASE"
set -x
sudo lxc-attach -n $CONTAINER_NAME -- mysql -u $DB_USER --password=$DB_PASS -e "drop database $DATABASE"
sudo lxc-attach -n $CONTAINER_NAME -- mysql -u $DB_USER --password=$DB_PASS -e "create database $DATABASE"
sudo lxc-attach -n $CONTAINER_NAME -- mysql -u $DB_USER --password=$DB_PASS $DATABASE < $DATASET_SEED
set +x

echo "Build test environment"
cd $CONTAINER_GIT_REPO_PATH

## We don't need a virtualenv as the container performs this
#echo "Setting up virtual env"
#source ~/.bashrc
#source /etc/bash_completion.d/virtualenvwrapper
#rm -rf ~/.virtualenvs/$UNIQUE_ID
#mkvirtualenv $UNIQUE_ID
#toggleglobalsitepackages
#sudo lxc-attach -n $CONTAINER_NAME -- export PYTHONPATH=$PYTHONPATH:$GIT_REPO_PATH:$WORKING_PATH/python_packages

# zuul puts us in a headless mode, lets check it out into a working branch
git branch -D working 2> /dev/null
git checkout -b working

stable_release_db_sync

get_db_version
last_stable_version=$VERSION
echo "Schema after stable_release_db_sync version is $last_stable_version"

# Make sure the test DB is up to date with trunk
if [ `git show | grep "^\-\-\-" | grep "migrate_repo/versions" | wc -l` -gt 0 ]
then
  echo "This change alters an existing migration, skipping trunk updates."
else
  echo "Update database to current state of trunk"
  git checkout master
  pip_requires
  db_sync "trunk"
  git checkout working
fi

# Now run the patchset
echo "Now test the patchset"
pip_requires
db_sync "patchset"

# Determine the schema version
get_db_version
echo "Schema version is $VERSION"

echo "Now downgrade all the way back to the last stable version (v$last_stable_version)"
db_sync "patchset" "--version $last_stable_version"

# Determine the schema version
get_db_version
echo "Schema version is $VERSION"

echo "And now back up to head from the start of trunk"
git checkout working  # I think this line is redundant
db_sync "patchset"

# Determine the final schema version
get_db_version
echo "Final schema version is $VERSION"

if [ "%$NOCLEANUP%" == "%%" ]
then
  # Cleanup virtual env
  # echo "Cleaning up virtual env"
  #deactivate
  #rmvirtualenv $UNIQUE_ID
  sudo lxc-stop -n $CONTAINER_NAME
  sudo lxc-destroy -n $CONTAINER_NAME
fi
