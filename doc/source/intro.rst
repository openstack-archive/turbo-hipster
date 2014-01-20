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
 report back to Zuul automatically.

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
the connection between Zuul and turbo-hipster, recognizing when a job
matches the rule, and passing it to turbo-hipster for testing. When turbo-
hipster receives the patchset for the job, it creates a virtual environment
to test it. The result of the test is sent back to Gearman as a json string,
which contains links to compiled logfiles.

The simplified workflow for turbo-hipster:

1. Registers as a worker against Zuul's Gearman server
2. Receives jobs from Zuul as they arrive
3. Checks out the patchset
4. Sets up a new virtual environment for testing
5. Loads a representative subset of the available datasets
6. Runs the migration against each dataset, and checks the result
7. Reports the results to Zuul, using the Gearman protocol

Typical workflow diagram
------------------------

.. seqdiag::

   seqdiag admin {
      # define order of elements
      # seqdiag sorts elements by order they appear
      humanoid; gerrit; zuul; gearman; turbo-hipster1; turbo-hipster2;

      humanoid -> gerrit [leftnote = "Patchset uploaded"];

      zuul -> gearman [label = "register-server"];
      zuul <-- gearman;

      turbo-hipster1 -> gearman [label = "add server"];
      turbo-hipster1 <-- gearman;
      turbo-hipster1 -> gearman [label = "register functions"];
      turbo-hipster1 <-- gearman;

      turbo-hipster2 -> gearman [label = "add server"];
      turbo-hipster2 <-- gearman;
      turbo-hipster2 -> gearman [label = "register functions"];
      turbo-hipster2 <-- gearman;


      gerrit -> zuul [label = "patchset-uploaded"];
      zuul -> gearman [label = "request worker"];
      zuul -> gearman [label = "request worker"];
      gearman -> turbo-hipster1 [label = "run function"];
      gearman -> turbo-hipster2 [label = "run function"];
      gearman <- turbo-hipster1 [label = "return result"];
      gearman <- turbo-hipster2 [label = "return result"];
      zuul <- gearman [label = "return result"];
      zuul <- gearman [label = "return result"];
      gerrit <- zuul [label = "voting results"];

      humanoid <-- gerrit;

   }


