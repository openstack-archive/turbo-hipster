#!/bin/bash

source $1/bin/activate
shift
nova-manage $@
