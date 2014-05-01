#!/bin/bash

# Generate a baseline measure of the performance of an instance

# $1 is a string descript of the instance flavor

echo "Instance flavor: $1"
echo "IO test starts"
time dd if=/dev/zero bs=1024000 count=1024 of=/tmp/test-$$.dd
rm -f /tmp/test-$$.dd
echo "IO test ends"
