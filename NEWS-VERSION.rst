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



