Stop depending on Servarr for download client authentication, requires configuration
changes.

Radarr no longer returns passwords from the download client API endpoint.  Following
their lead, stop depending on the Servarr APIs to provide authentication credentials and
get the Transmission RPC password from the Prunerr configuration::

  ...
  download-clients:
    urls:
      - "https://transmission:secret@transmission.example.com"
  ...
