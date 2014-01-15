Turbo-hipster
=============

Turbo-hipster works with the existing OpenStack code review system to
implement testing-related plugins. Historically, whenever code has been
written for Nova it has been tested against trivial datasets rather than
real data. This can mean that when users run the updated code on their
databases they can run into issues that were not found during testing. A
variety of real-world databases have been collected, anonymized, and added
to the database migration plugin used by turbo-hipster. Turbo-hipster is
integrated into the existing code review system, and automatically runs
tests against these larger test datasets. Turbo-hipster is specifically
designed to flag issues where changes to the database schema may not work
due to outliers in real datasets, and to identify situations where a
migration may take an unreasonable amount of time against a large database.

.. note::
 Database anonymity is important, and can be very time consuming.
 The databases used by turbo-hipster to test against are real-world databases
 that have been anonymized with a database anonymization tool called Fuzzy
 Happiness. Fuzzy Happiness takes markup in the sqlalchemy models file and
 uses that to decide what values to anonymize, and how to do so. This feature
 is still in development, and until it is complete turbo-hipster will not
 report back to Zuul automatically. See the Release Notes for more detail.

Additionally, turbo-hipster has been designed to be extensible, so it is
possible to write other plugins to expand its capabilities.

Turbo-hipster and Zuul
----------------------

Turbo-hipster is a Gearman worker. Zuul provides arguments that turbo-
hipster uses to check out the patch, perform the database testing, and then
report back with success or failure. Zuul allows you to specify which jobs
should be run against which projects. You can create a rule in Zuul for it
to select jobs that require testing against a database. Turbo-hipster will
then register as being able to complete that type of job. Gearman handles
the connection between Zuul and Turbo-Hipster, recognizing when a job
matches the rule, and passing it to turbo-hipster for testing. When turbo-
hipster receives the patchset for the job, it creates a virtual environment
to test it. The result of the test is sent back to Gearman as a json string,
which contains links to compiled logfiles.

The simplified workflow for Turbo-Hipster:

1. Registers as a worker against Zuul's Gearman server
2. Receives jobs from Zuul as they arrive
3. Checks out the patchset
4. Sets up a new virtual environment for testing
5. Loads in a representative subset of the available datasets
6. Runs the migration against each dataset, and checks the result
7. Reports the results to Zuul, using the Gearman protocol

Typical workflow diagram
------------------------

**clearly this needs a lot of work, however I believe the structure
is mostly there... If you know graphviz please help!**

.. graphviz::

   digraph overview {
       subgraph cluster_1 {
            label = "Gerrit"
            style = filled;
            color = lightgrey;
            node [style=filled,color=white];

            g000 [shape=Mdiamond label="start"];
            g001 [shape=box, label="receive event"];
            g002 [shape=box, label="notify listeners"];

            g000 -> g001;
            g001 -> g002;
            g002 -> g001;
       }

       subgraph cluster_2 {
            label = "Zuul pipeline";
            color = blue
            node [style=filled];

            z000 [shape=Mdiamond label="start"];
            z001 [shape=box, label="register gearman server"];
            z002 [shape=box, label="register launchers"];
            z003 [shape=box, label="listen for events"];
            z004 [shape=box, label="receive event"];
            z005 [shape=box, label="request jobs"];
            z006 [shape=box, label="receive response"];
            z007 [shape=box, label="send report"];

            z000 -> z001 -> z002;
            z003 -> z004 -> z005;
            z005 -> z006 [dir=none, style=dotted];
            z006 -> z007;

       }

       subgraph cluster_3 {
            label = "Gearman";
            style = filled;
            color = lightgrey;
            node [style=filled,color=white];

            gm001 [shape=box, label="receive job method"];
            gm002 [shape=box, label="request worker do method"];
            gm003 [shape=box, label="receive results"];
            gm004 [shape=box, label="return results"];

            gms000 [label="register client"];
            gms001 [label="register worker"];
            gms002 [label="register method"];

            gm001 -> gm002;
            gm002 -> gm003 [dir=none, style=dotted];
            gm003 -> gm004;
       }

       subgraph cluster_4 {
            label = "Turbo Hipster";
            color = blue
            node [style=filled];

            th000 [shape=Mdiamond label="start"];
            th001 [shape=box, label="register as worker"];
            th002 [shape=box, label="find available tasks"];
            th003 [shape=box, label="register available job methods"];

            ths001 [shape=box, label="receive method request"];
            ths002 [shape=box, label="run task"];
            ths003 [shape=box, label="send results"];

            th000 -> th001 -> th002 -> th003;
            ths001 -> ths002 -> ths003;
       }

       z001 -> gms000;
       z005 -> gm001;
       gm004 -> z006;
       z003 -> g002 [dir=both, style=dotted];
       th001 -> gms001;
       th003 -> gms002;
       gm002 -> ths001;
       ths003 -> gm003;

   }

Installation
============

Turbo-hipster is installed directly into your Python ``site-packages``
directory, and is then run as a service. It is managed using a configuration
file, which is in .json format.

Installing turbo-hipster
------------------------

1. Turbo-Hipster can be installed directly to your Python ``site-packages``
directory::

 $ sudo python setup.py install

2. Copy the configuration file to a convenient location. By default,
turbo-hipster will look in ``/etc/turbo-hipster/config.json`` ::

 $ cp -R etc/turbo-hipster /etc/

3. The Turbo-Hipster configuration file is in .json format. Open the
``config.json`` configuration file in your preferred editor and modify it
for your environment::

  **zuul_server**
    A dictionary containing details about how to communicate
    with zuul
       **git_url**
           The publicly accessible protocol and URI from where
           to clone projects and zuul_ references from. For
           example::
               http://review.openstack.org/p/
           or::
               git://review.example.org
       **gearman_host**
           The host of gearman_. zuul talks to its workers via
           the gearman protocol and while it comes with a built-
           in gearman server you can use a separate one.
       **gearman_port**
           The port that gearman listens on.
  **debug_log**
    A path to the debug log. Turbo-hipster will attempt to create
    the file but must have write permissions.
  **jobs_working_dir**
    Each job will likely need to write out log and debug
    information. This defines where turbo-hipster will do that.
  **git_working_dir**
    turbo-hipster needs to take a copy of the git tree of a
    project to work from. This is the path it'll clone into and
    work from (if needed).
  **pip_download_cache**
    Some of turbo-hipsters task plugins download requirements
    for projects. This is the cache directory used by pip.
  **plugins**
    A list of enabled plugins and their settings in a dictionary.
    The only required parameters are *name*, which should be the
    same as the folder containing the plugin module, and
    *function*, which is the function registered with zuul.
    Any other parameters are specified by the plugin themselves
    as required.
  **publish_logs**
    Log results from plugins can be published using multiple
    methods. Currently only a local copy is fully implemented.
       **type**
           The type of protocol to copy the log to. eg 'local'
       **path**
           A type specific parameter defining the local location
           destination.
       **prepend_url**
           What to prepend to the path when sending the result
           URL back to zuul. This can be useful as you may want
           to use a script to authenticate against a swift
           account or to use *laughing_spice* to format the logs
           etc.

4. Create a turbo-hipster user:

 $ useradd turbo-hipster

5. Create the directories listed in the configuration file, and give the
``turbo-hipster`` user write access::

 $ mkdir -p /var/log/turbo-hipster/
 $ chown turbo-hipster:turbo-hipster /var/log/turbo-hipster/

 $ mkdir -p /var/lib/turbo-hipster/jobs
 $ chown turbo-hipster:turbo-hipster /var/lib/turbo-hipster/jobs

 $ mkdir -p /var/lib/turbo-hipster/git
 $ chown turbo-hipster:turbo-hipster /var/lib/turbo-hipster/git

 $ mkdir -p /var/cache/pip
 $ chown turbo-hipster:turbo-hipster /var/cache/pip

6. Open the MySQL log rotation configuration file in your preferred text
editor, and edit it to ensure it is writable by ``other``::

 $ vim /etc/logrotate.d/mysql-server
 # edit create 640 to 644.

.. note::
  The turbo-hipster source code is also available for download from
  the `turbo-hipster github page <https://github.com/rcbau/turbo-hipster/>`_ 

  $ git clone https://github.com/rcbau/turbo-hipster

Starting turbo-hipster
----------------------

Turbo-hipster can be run from the command line::

 $ ./turbo-hipster/worker_server.py

This option allows you to pass parameters to turbo-hipster. Use the --help
parameter to see a full list.

+-------+--------------+--------------------------------------------------------+
| Short |    Long      | Description                                            |
+=======+==============+========================================================+
|  -c   | --config     | Print the path to the configuration file and exit      |
+-------+--------------+--------------------------------------------------------+
|  -b   | --background | Run as a daemon in the background                      |
+-------+--------------+--------------------------------------------------------+
|  -p   | --pidfile    | Specify the PID file to lock while running as a daemon |
+-------+--------------+--------------------------------------------------------+

Alternatively, you can start turbo-hipster as a service.

1. Copy the turbo-hipster init.d script to /etc/init.d/::

 $ sudo cp etc/init.d/turbo-hipster /etc/init.d/

2. Reload the script with the default configuration::

 $ sudo update-rc.d turbo-hipster defaults

3. Start the service::

 $ sudo service turbo-hipster start

Plugins
=======

Plugins can be used to extend turbo-hipster's capabilities.

.. note::
 Currently, the only available plugin for turbo-hipster is the
 Database Migration plugin, ``gate_real_db_upgrade``, which tests code
 against a variety of real-world databases.

Installing plugins
------------------

Turbo-hipster plugins are responsible for handling the jobs that are passed
to it. They must successfully build reports and publish them according to
their configuration. They must also be able to communicate test results back
to Zuul using Gearman.

Plugins must take a standard format in order to be able to work correctly
with turbo-hipster. They must contain a ``task.py`` file with a ``Runner``
class.

Once you have created a turbo-hipster plugin, you need to configure it in
the ``config.json`` configuration file.

.. FIXME More config information required here

Plugin: Database migration with ``gate_real_db_upgrade``
--------------------------------------------------------

The database migration plugin, ``gate_real_db_upgrade``, is used to test
datasets against real-world, anonymized, databases.

Migrating a database
--------------------

In order to use turbo-hipster with the ``gate_real_db_upgrade`` plugin, you
need to set up the databases to test against, and point to the plugin in
turbo-hipster's configuration file.

1. Create a directory for the datasets::

 $ mkdir -p /var/lib/turbo-hipster/datasets
 
2. Copy the json dataset to the directory you created::

 $ cp /my/dataset.json /var/lib/turbo-hipster/datasets/

3. Open the ``/etc/turbo-hipster/config.json`` file in your preferred
editor, locate the plugins section, and add this line::

  **plugins**
   gate_real_db_upgrade

Testing with turbo-hipster
==========================

When turbo-hipster completes a test, it sends the result of the test back to
Gearman. These results contain a link to a compiled logfile for the test.

If the test fails, or takes too long to complete, turbo-hipster will add a
review to your patchset that looks like this:

.. image:: ../images/THTestResult.png

Reading test reports
--------------------

An example of a standard log file:
http://thw01.rcbops.com/results/54/54202/5/check/gate-real-db-upgrade_nova_mysql_devstack_150/ddd6d53/20130910_devstack_applied_to_150.log

An example of the same logfile, using the javascript logviewer:
http://thw01.rcbops.com/logviewer/?q=/results/54/54202/5/check/gate-real-db-upgrade_nova_mysql_devstack_150/ddd6d53/20130910_devstack_applied_to_150.log

Test failure codes
------------------

This section gives a list of failure codes, including some steps you can
take for troubleshooting errors:

 FAILURE - Did not find the end of a migration after a start

If you look at the log you should find that a migration began but never
finished. Hopefully there'll be a traceroute for you to follow through to
get some hints about why it failed.

 WARNING - Migration %s took too long

In this case your migration took a long time to run against one of the test
datasets. You should reconsider what operations your migration is performing
and see if there are any optimizations you can make, or if it is really
necessary. If there is no way to speed up your migration you can email us at
rcbau@rcbops.com for an exception.

 FAILURE - Final schema version does not match expectation

Somewhere along the line the migrations stopped and did not reach the
expected version. Our datasets start at previous releases and have to
upgrade all the way through to the most current release. If you see this,
inspect the log for traceroutes or other hints about the failure.

 FAILURE - Could not setup seed database.
 FAILURE - Could not find seed database.

These errors are internal errors. If you see either of these, contact us at
rcbau@rcbops.com to let us know so we can fix and rerun the tests for you.

 FAILURE - Could not import required module.

This error probably shouldn't happen as Jenkins should catch it in the unit
tests before Turbo-Hipster launches. If you see this, please contact us at
rcbau@rcbops.com and let us know.

If you receive an error that you think is a false positive, leave a comment
on the review with the sole contents of "recheck migrations".

If you have any questions/problems please contact us at rcbau@rcbops.com.