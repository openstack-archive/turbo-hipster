#!/bin/bash

# Create a network namespace with no network access
sudo ip netns add nonet 
sudo ip link add veth0 type veth peer name veth1
sudo ifconfig veth0 172.16.0.1/24 up
sudo ip link set veth1 netns nonet
sudo ip netns exec nonet ifconfig veth1 172.16.0.2/24 up

# Firewall mysql connections from outside
sudo /sbin/iptables -A INPUT -p tcp --dport 3306 ! -d 127.0.0.1 -j DROP
sudo /sbin/iptables -A INPUT -p tcp --dport 3306 ! -d 172.16.0.1 -j DROP
