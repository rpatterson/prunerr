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



