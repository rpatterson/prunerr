prunerr 3.0.0b0 (2023-11-09)
============================

Features
--------

- Add support for setting the download client's timeout.  This involves adding support for
  configuring each download client individually, as opposed to only a list of URLs, and as
  such requires a configuration change::

    ...
    download-clients:
      Transmission:
        url: "http://transmission:secret@localhost:9091/transmission/"
        timeout: "30.0"
        max-download-bandwidth: 100
        min-download-time-margin: 600
    ...


prunerr 2.0.0 (2023-11-01)
==========================

No significant changes.


prunerr 2.0.0b4 (2023-10-31)
============================

Bugfixes
--------

- Fix the CI/CD release process.


prunerr 2.0.0b3 (2023-10-31)
============================

Bugfixes
--------

- Upgrade all requirements to the most recent versions as of
  Tue Oct 31 05:01:35 PM UTC 2023.


prunerr 2.0.0b2 (2023-10-30)
============================

Bugfixes
--------

- Fix handling of empty top-level keys in the configuration file::

    DEBUG:prunerr.runner:Sub-command `exec` completed in 89.50181317329407s
    Traceback (most recent call last):
      File "/usr/local/bin/prunerr", line 8, in <module>
        sys.exit(main())
                 ^^^^^^
      File "/usr/local/lib/python3.11/site-packages/prunerr/__init__.py", line 241, in main
        _main(args=args)
      File "/usr/local/lib/python3.11/site-packages/prunerr/__init__.py", line 288, in _main
        if (result := parsed_args.command(runner, **command_kwargs)) is not None:
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File "/usr/local/lib/python3.11/site-packages/prunerr/__init__.py", line 181, in daemon
        runner.daemon(*args, **kwargs)
      File "/usr/local/lib/python3.11/site-packages/prunerr/runner.py", line 337, in daemon
        poll = self.config.get("daemon", {}).get("poll", 60)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    AttributeError: 'NoneType' object has no attribute 'get'
- Get default values from `the example configuration file
  <https://gitlab.com/rpatterson/prunerr/blob/main/src/prunerr/home/.config/prunerr.yml>`_.


prunerr 2.0.0b1 (2023-10-29)
============================

Bugfixes
--------

- Trigger a release after the v2.0.0b0 release failure.


prunerr 2.0.0b0 (2023-10-29)
============================

Features
--------

- Update `the Python versions <https://www.python.org/downloads/>`_ this package supports.
  Remove v3.7 support and add v3.12 support.
- Update the default supported Python version from v3.10 to v3.11.  Match the default
  version in `the official Python Docker image <https://hub.docker.com/_/python>`_.


Bugfixes
--------

- Don't hide connection errors in output logs at the default logging level.
- Normalize the port in download client URLs so that they match regardless of whether the
  default port for the protocol or scheme, ``80`` vs ``443``, is specified.
- Stop depending on Servarr for download client authentication, requires configuration
  changes.

  Radarr no longer returns passwords from the download client API endpoint.  Following
  their lead, stop depending on the Servarr APIs to provide authentication credentials and
  get the Transmission RPC password from the Prunerr configuration::

    ...
    download-clients:
      urls:
        - "https://transmission:secret@transmission.example.com"
    ...
- Tolerate connection timeouts with external services when performing review actions on a
  per-item basis to minimize the interruptions from intermittent errors.
- Upgrade all requirements to the most recent versions as of
  Sun Oct 29 06:24:32 PM UTC 2023.


prunerr 1.1.13 (2023-05-10)
===========================

No significant changes.


prunerr 1.1.13b2 (2023-05-10)
=============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Wed May 10 06:49:51 PM UTC 2023.


prunerr 1.1.13b1 (2023-05-10)
=============================

No significant changes.


prunerr 1.1.13b0 (2023-05-10)
=============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Tue May  9 09:31:01 PM UTC 2023.


prunerr 1.1.12 (2023-05-08)
===========================

Bugfixes
--------

- Fix pushing README to Docker Hub.


prunerr 1.1.11 (2023-05-08)
===========================

No significant changes.


prunerr 1.1.11b0 (2023-05-08)
=============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Sun May  7 09:27:36 AM UTC 2023.


prunerr 1.1.10 (2023-05-06)
===========================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Sat May  6 17:01:32 UTC 2023.


prunerr 1.1.9 (2023-05-06)
==========================

No significant changes.


prunerr 1.1.9b1 (2023-05-05)
============================

Bugfixes
--------

- Workaround the broken previous release not being published.


prunerr 1.1.9b0 (2023-05-05)
============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Fri May  5 01:58:13 PM UTC 2023.


prunerr 1.1.8 (2023-04-27)
==========================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Thu Apr 27 18:36:06 UTC 2023.


prunerr 1.1.7 (2023-04-26)
==========================

No significant changes.


prunerr 1.1.6 (2023-04-26)
==========================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Wed Apr 26 05:24:13 PM UTC 2023.


prunerr 1.1.5 (2023-04-26)
==========================

No significant changes.


prunerr 1.1.5b0 (2023-04-26)
============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Tue Apr 25 11:00:28 PM UTC 2023.


prunerr 1.1.4 (2023-04-25)
==========================

No significant changes.


prunerr 1.1.4b0 (2023-04-25)
============================

Improved Documentation
----------------------

- Link important use cases to their corresponding example configuration.


prunerr 1.1.3 (2023-04-24)
==========================

No significant changes.


prunerr 1.1.3b0 (2023-04-24)
============================

No significant changes.


prunerr 1.1.2 (2023-04-22)
==========================

No significant changes.


prunerr 1.1.2b2 (2023-04-22)
============================

No significant changes.


prunerr 1.1.2b1 (2023-04-20)
============================

No significant changes.


prunerr 1.1.2b0 (2023-04-18)
============================

No significant changes.


prunerr 1.1.1 (2023-04-16)
==========================

No significant changes.


prunerr 1.1.1b0 (2023-04-16)
============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Sun Apr 16 03:54:21 PM UTC 2023.


prunerr 1.1.0 (2023-04-15)
==========================

No significant changes.


prunerr 1.1.0b27 (2023-04-15)
=============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Sat Apr 15 06:11:17 PM UTC 2023.


prunerr 1.1.0b26 (2023-04-14)
=============================

No significant changes.


prunerr 1.1.0b25 (2023-04-14)
=============================

No significant changes.


prunerr 1.1.0b24 (2023-04-11)
=============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Tue Apr 11 08:15:25 PM UTC 2023.


prunerr 1.1.0b23 (2023-04-10)
=============================

Bugfixes
--------

- Upgrade all requirements to the latest versions as of Sun Apr  9 11:19:15 PM UTC 2023.


Prunerr 1.1.0b22 (2023-03-01)
=============================

Features
--------

- Reduce memory consumption by clearing cached download client and Servarr data.


Bugfixes
--------

- Workaround incorrect timestamps causing ``ZeroDivisionError`` while reviewing items.
- Also verify running items with the correct error, not only paused/stopped items.


Misc
----

- lint-missing-reports


Prunerr 1.1.0b21 (2023-02-25)
=============================

No significant changes.


Prunerr 1.1.0b20 (2023-02-24)
=============================

No significant changes.


Prunerr 1.1.0b19 (2023-02-24)
=============================

No significant changes.


Prunerr 1.1.0b18 (2023-02-24)
=============================

No significant changes.


Prunerr 1.1.0b17 (2023-02-24)
=============================

No significant changes.


Prunerr 1.1.0b16 (2023-02-22)
=============================

No significant changes.


Prunerr 1.1.0b15 (2023-02-22)
=============================

Misc
----

- ci-gitlab-debug-linter-diff


Prunerr 1.1.0b14 (2023-02-22)
=============================

Misc
----

- ci-missing-volume, ci-missing-volume-2


Prunerr 1.1.0b13 (2023-02-22)
=============================

No significant changes.


Prunerr 1.1.0b12 (2023-02-21)
=============================

Misc
----

- various-test-ci


Prunerr 1.1.0b11 (2023-02-21)
=============================

Features
--------

- Support all currently maintained versions of Python.


Prunerr 1.1.0b10 (2023-01-27)
=============================

No significant changes.


Prunerr 1.1.0b9 (2023-01-23)
============================

No significant changes.


Prunerr 1.1.0b8 (2023-01-23)
============================

No significant changes.


Prunerr 1.1.0b7 (2023-01-23)
============================

No significant changes.


Prunerr 1.1.0b6 (2023-01-13)
============================

No significant changes.


Prunerr 1.1.0b5 (2022-12-20)
============================

Bugfixes
--------

- Expand which error strings are used to identify unregistered download items.


Prunerr 1.1.0b4 (2022-12-19)
============================

No significant changes.


Prunerr 1.1.0b3 (2022-12-18)
============================

Features
--------

- Return CLI results as JSON.


Prunerr 1.1.0b2 (2022-12-18)
============================

No significant changes.


Prunerr 1.1.0b1 (2022-12-17)
============================

No significant changes.


Prunerr 1.1.0b0 (2022-12-16)
============================

Features
--------

- Add ``--log-level`` CLI option to give the user more control over output verbosity.


Bugfixes
--------

- Don't report ``review`` results from the ``exec`` sub-command when there are none.


Prunerr 1.0.0 (2022-12-13)
==========================

No significant changes.


Prunerr 1.0.0b4 (2022-12-13)
============================

No significant changes.


Prunerr 1.0.0b3 (2022-12-12)
============================

No significant changes.


Prunerr 1.0.0b2 (2022-12-12)
============================

Features
--------

- First official release that may be suitable for end users.
