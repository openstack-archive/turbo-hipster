:title:Turbo Hipster Structure

Structure
=======================

Plugins
-------

A little bit about plugins to come here soon.

 - You need to configure it in config.json
 - Folder name must be the same as 'name'
 - You probably want to specify a gate in the config
    - see something (introduction?) about gates and how turbo-hipster
      uses them
 - Each plugin has a task.py with a Runner class
    - Responsible for registering functions
    - handling jobs
    - checking for errors
    - building reports
    - publishing them according to configuration
