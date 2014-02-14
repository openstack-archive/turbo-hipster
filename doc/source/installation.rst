:title: Installation

.. _gearman: http://gearman.org/
.. _zuul: http://ci.openstack.org/zuul/

Installation
============

Turbo-hipster is installed directly into your Python ``site-packages``
directory, and is then run as a service. It is managed using a configuration
file, which is in json format.

Installing turbo-hipster
------------------------

1. Turbo-hipster can be installed directly to your Python ``site-packages``
directory:

 $ sudo python setup.py install

2. Copy the configuration file to a convenient location. By default,
turbo-hipster will look in ``/etc/turbo-hipster/config.json``:

 $ cp -R etc/turbo-hipster /etc/

3. The turbo-hipster configuration file is in json format. Open the
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
  **conf_d**
    A path of a directory containing peices of json confiuration. 
    This is helpful when you want different plugins to add extra 
    or even modify the default configuration. 

4. Create a turbo-hipster user:

 $ useradd turbo-hipster

5. Create the directories listed in the configuration file, and give the
``turbo-hipster`` user write access:

 $ mkdir -p /var/log/turbo-hipster/
 $ chown turbo-hipster:turbo-hipster /var/log/turbo-hipster/

 $ mkdir -p /var/lib/turbo-hipster/jobs
 $ chown turbo-hipster:turbo-hipster /var/lib/turbo-hipster/jobs

 $ mkdir -p /var/lib/turbo-hipster/git
 $ chown turbo-hipster:turbo-hipster /var/lib/turbo-hipster/git

 $ mkdir -p /var/cache/pip
 $ chown turbo-hipster:turbo-hipster /var/cache/pip

6. Open the MySQL log rotation configuration file in your preferred text
editor, and edit it to ensure it is writable by ``other``:

 $ vim /etc/logrotate.d/mysql-server
 # edit create 640 to 644.

.. note::
  The turbo-hipster source code is also available for download from
  the `turbo-hipster github page <https://github.com/rcbau/turbo-hipster/>`_

  $ git clone https://github.com/rcbau/turbo-hipster

.. note::
 Debug logging must be configured for turbo-hipster, as it uses the Python
 logging framework to capture log messages from the task plugin code.
 To configure debug logging, set the ``debug_log`` configuration
 setting in the ``config.json`` configuration file.
