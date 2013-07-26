#!/bin/bash

# $1 is the safe refs URL
# $2 is the path to the git repo
# $3 is the nova db user
# $4 is the nova db password
# $5 is the nova db name

pip_requires() {
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
  # $2 is the path to the git repo
  # $3 is the nova db user
  # $4 is the nova db password
  # $5 is the nova db name

  # Create a nova.conf file
  cat - > $2/nova-$1.conf <<EOF
[DEFAULT]
sql_connection = mysql://$3:$4@localhost/$5?charset=utf8
log_config = /srv/openstack-ci-tools/logging.conf
EOF

  find $2 -type f -name "*.pyc" -exec rm -f {} \;

  nova_manage="$2/bin/nova-manage"
  if [ -e $nova_manage ]
  then
    echo "***** DB upgrade to state of $1 starts *****"
    python $nova_manage --config-file $2/nova-$1.conf db sync
  else
    python setup.py clean
    python setup.py develop
    echo "***** DB upgrade to state of $1 starts *****"
    nova-manage --config-file $2/nova-$1.conf db sync
  fi
  echo "***** DB upgrade to state of $1 finished *****"
}

echo "To execute this script manually, run this:"
echo "$0 $1 $2 $3 $4 $5"

set -x

# Setup the environment
export PATH=/usr/lib/ccache:$PATH
export PIP_DOWNLOAD_CACHE=/srv/cache/pip

# Restore database to known good state
echo "Restoring test database $5"
mysql --defaults-file=/srv/config/mysql -u root -e "drop database $5"
mysql --defaults-file=/srv/config/mysql -u root -e "create database $5"
mysql --defaults-file=/srv/config/mysql -u root -e "create user '$3'@'localhost' identified by '$4';"
mysql --defaults-file=/srv/config/mysql -u root -e "grant all privileges on $5.* TO '$3'@'localhost';"
mysql -u $3 --password=$4 $5 < /srv/datasets/$5.sql

echo "Build test environment"
cd $2

set +x
echo "Setting up virtual env"
source ~/.bashrc
source /etc/bash_completion.d/virtualenvwrapper
rm -rf ~/virtualenvs/$1
mkvirtualenv $1
toggleglobalsitepackages
set -x
export PYTHONPATH=$PYTHONPATH:$2

# Some databases are from Folsom
version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Schema version is $version"
if [ $version == "133" ]
then
  echo "Database is from Folsom! Upgrade via grizzly"
  git checkout stable/grizzly
  pip_requires
  db_sync "grizzly" $2 $3 $4 $5
fi

# Make sure the test DB is up to date with trunk
git checkout target
if [ `git show | grep "^\-\-\-" | grep "migrate_repo/versions" | wc -l` -gt 0 ]
then
  echo "This change alters an existing migration, skipping trunk updates."
else
  echo "Update database to current state of trunk"
  git checkout trunk
  pip_requires
  db_sync "trunk" $2 $3 $4 $5
  git checkout target
fi

# Now run the patchset
echo "Now test the patchset"
pip_requires
db_sync "patchset" $2 $3 $4 $5

# Determine the final schema version
version=`mysql -u $3 --password=$4 $5 -e "select * from migrate_version \G" | grep version | sed 's/.*: //'`
echo "Final schema version is $version"

# Cleanup virtual env
set +x
echo "Cleaning up virtual env"
deactivate
rmvirtualenv $1
echo "done" > /srv/logs/$1
