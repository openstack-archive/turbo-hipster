turbo-hipster
=============

A set of CI tools.

worker_server.py is a worker server that loads and runs task_plugins.

Each task_plugin is a zuul gearman worker that implements, handles, executes a
job, uploads/post-processes the logs and sends back the results to zuul.

plugins
-------

**gate_real_db_upgrade**:
Runs the db_sync migrations on each dataset available in the datasets subdir.