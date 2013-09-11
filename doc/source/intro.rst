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

zuul integration
----------------

Explain how zuul triggers builds and gates etc and how turbo-hipster
responds to them. Most of this is in the zuul documentation so don't
duplicate.
