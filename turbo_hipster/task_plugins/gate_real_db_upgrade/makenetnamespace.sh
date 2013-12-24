#!/bin/bash

# Create a network namespace with no network access
sudo ip netns add nonet
sudo ip link add veth0 type veth peer name veth1
sudo ifconfig veth0 172.16.0.1/24 up
sudo ip link set veth1 netns nonet
sudo ip netns exec nonet ifconfig veth1 172.16.0.2/24 up

# Firewall mysql connections from outside
sudo /sbin/iptables -A INPUT -p tcp --dport 3306 -i eth0 -j DROP
sudo /sbin/iptables -A INPUT -p tcp --dport 3306 -i eth1 -j DROP

# Mysql permissions
mysql -u root --password=$1 -e "create user 'nova'@'172.16.0.2' identified by 'tester';"
mysql -u root --password=$1 -e "grant all privileges on *.* to 'nova'@'172.16.0.2' with grant option;"
