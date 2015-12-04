turbo-hipster
=============

A set of CI tools.

worker_server.py is a worker server that loads and runs task_plugins.

Each task_plugin is a zuul gearman worker that implements, handles, executes a
job, uploads/post-processes the logs and sends back the results to zuul.

Plugins
-------

**gate_real_db_upgrade**:
Runs the db_sync migrations on each dataset available in the datasets subdir.

Installation
------------

* boot a fresh Ubuntu image
* setup ssh authentication for your admin team
* apt-get update; apt-get dist-upgrade
* adduser th
* apt-get install vim git python-pip python-setuptools python-keystoneclient virtualenvwrapper python-eventlet python-numpy python-mysqldb python-git python-gitdb python-netaddr python-pkg-resources libxml2-dev libxml2-utils libxslt-dev git-review libxml2-dev libxml2-utils libxslt-dev libmysqlclient-dev pep8 postgresql-server-dev-9.1 python2.7-dev python-coverage python-netaddr
* pip install -U pip 
* apt-get purge python-pip
* cd /home/th; git clone http://github.com/openstack/turbo-hipster
* apply any patches you need
* python setup.py install
* cp turbo_hipster/task_plugins/gate_real_db_upgrade/*.sh /usr/local/lib/python2.7/dist-packages/turbo_hipster/task_plugins/gate_real_db_upgrade/
* cp -R etc/* /etc/
* mkdir /var/lib/turbo-hipster
* chown -R th.th /var/lib/turbo-hipster
* mkdir /var/log/turbo-hipster
* chown -R th.th /var/log/turbo-hipster
* install your chosen MySQL-like database engine (percona, maria, mysql)
* mysql -u root --password=$1 -e "create user 'nova'@'localhost' identified by 'tester';"
* mysql -u root --password=$1 -e "create user 'nova'@'172.16.0.2' identified by 'tester';"
* mysql -u root --password=$1 -e "grant all privileges on *.* to 'nova'@'localhost' with grant option;"
* mysql -u root --password=$1 -e "grant all privileges on *.* to 'nova'@'172.16.0.2' with grant option;"
* /etc/rc.local
* rsync the datasets from the master
* logrotate -f /etc/logrotate.conf
* chmod -R ugo+r /var/log/*
* chmod ugo+rx /var/log/mysql
* mkdir /var/cache/pip
* chmod -R ugo+rwx /var/cache/pip
* touch /var/log/mysql/slow-queries.log
* /etc/init.d/turbo-hipster start