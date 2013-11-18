:title: Installation

.. _gearman: http://gearman.org/
.. _zuul: http://ci.openstack.org/zuul/

Installation
============

Download
--------

Grab a copy from https://github.com/rcbau/turbo-hipster


Install
-------

turbo-hipster is configured to use setup tools for installation if
you would like to install it to your site-packages use::

    sudo python setup.py install


Copy config
-----------

Place the configuration where you are comfortable managing it. For
example::

    cp -R etc/turbo-hipster /etc/


Edit config
-----------

Turbo-hipsters configuration is currently stored in json format.
Modify the config.json appropriately::

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
        The only required parameter is *name* which should be the
        same as the folder containing the plugin module. Any other
        parameters are specified by the plugin themselves as
        required.
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


Set up
------

You probably want to create a user to run turbo-hipster as. This user
will need to write to all of the directories specified in
config.json.

Make sure the required directories as defined by the config.json
exist and are writeable by your turbo-hipster user::

    mkdir -p /var/log/turbo-hipster/
    chown turbo-hipster:turbo-hipster /var/log/turbo-hipster/

    mkdir -p /var/lib/turbo-hipster/jobs
    chown turbo-hipster:turbo-hipster /var/lib/turbo-hipster/jobs

    mkdir -p /var/lib/turbo-hipster/git
    chown turbo-hipster:turbo-hipster /var/lib/turbo-hipster/git

    mkdir -p /var/cache/pip
    chown turbo-hipster:turbo-hipster /var/cache/pip

Edit MySQL's log rotate to ensure it is other writable::

    vim /etc/logrotate.d/mysql-server
    # edit create 640 to 644.


Start turbo-hipster
-------------------

turbo hipster can be ran by executing::

    ./turbo-hipster/worker_server.py

and optionally takes the following parameters::

    ./turbo_hipster/worker_server.py --help
    usage: worker_server.py [-h] [-c CONFIG] [-b] [-p PIDFILE]

    optional arguments:
      -h, --help            show this help message and exit
      -c CONFIG, --config CONFIG
                            Path to json config file.
      -b, --background      Run as a daemon in the background.
      -p PIDFILE, --pidfile PIDFILE
                            PID file to lock during daemonization.

By default turbo-hipster will look for
*/etc/turbo-hipster/config.json*

Alternatively turbo-hipster can be launched by init.d using the
included etc/init.d/turbo-hipster script::

    sudo cp etc/init.d/turbo-hipster /etc/init.d/
    sudo update-rc.d turbo-hipster defaults
    sudo service turbo-hipster start
