#!/bin/bash -x

# $1 is the db engine name, currently one of:
#    mysql
#    percona

git pull

# Percona support
apt-key adv --keyserver keys.gnupg.net --recv-keys 1C4CBDCDCD2EFD2A
cp etc/percona.list /etc/apt/sources.list.d/percona.list

apt-get update
apt-get dist-upgrade -y
apt-get install -y git python-pip libxml2-dev libxml2-utils libxslt-dev libmysqlclient-dev pep8 postgresql-server-dev-9.1 python2.7-dev python-coverage python-netaddr python-mysqldb $1-server python-git virtualenvwrapper python-numpy

mkdir -p /var/log/mysql
touch /var/log/mysql/slow-queries.log
chown mysql.mysql /var/log/mysql/slow-queries.log

chmod ugo+rx /var/log/mysql
chmod ugo+r /var/log/syslog /var/log/mysql/slow-queries.log /var/log/mysql/error.log

if [ -e /etc/logrotate.d/percona-server-server-5.5 ]
then
  rm /etc/logrotate.d/percona-server-server-5.5
fi
/usr/sbin/logrotate /etc/logrotate.conf

/etc/init.d/apparmor restart
/etc/init.d/mysql restart

mkdir -p /var/log/turbo-hipster
chown turbo-hipster:turbo-hipster /var/log/turbo-hipster

mkdir -p /var/lib/turbo-hipster
chown turbo-hipster:turbo-hipster /var/log/turbo-hipster

mysql -u root -e "create user 'nova'@'localhost' identified by 'tester';"
mysql -u root -e "grant all privileges on nova.* TO 'nova'@'localhost';"
