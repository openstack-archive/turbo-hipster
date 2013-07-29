turbo-hipster
=============

A set of CI tools.

worker_server.py is a worker server that loads and runs task_plugins.

Each task_plugin is a gearman worker that implements, handles and executes a
job.

plugins
-------

**gate_real_db_upgrade**:
Runs the db_sync migrations on each dataset available in the datasets subdir.