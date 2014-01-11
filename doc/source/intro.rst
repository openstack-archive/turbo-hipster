 :title:Introduction

Turbo Hipster
=============

Turbo Hipster is a gearman worker designed to run tests using zuul
as the gearman client. It is primarily aimed at running openstack
continuous integration tests against pre-existing datasets but can
be used to automate any tests with zuul.

Overview
--------

The zuul server receives jobs from a trigger requesting particular
jobs/tests to be ran. Turbo Hipster is able to provide a worker for
each of those jobs or a subset and report the success/failure back to
zuul. zuul will then collate responses from multiple workers and
build a report.

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

zuul integration
----------------

Explain how zuul triggers builds and gates etc and how turbo-hipster
responds to them. Most of this is in the zuul documentation so don't
duplicate.
