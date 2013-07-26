rcbau-ci
========

A set of CI tools used by RCBAU.

worker.py is a worker server that loads and runs task_plugins.

Each task_plugin is a gearman worker that implements, handles and executes a
job.