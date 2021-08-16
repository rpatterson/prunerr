#######
Prunerr
#######
Remove Servarr download client items to preserve disk space according to rules.
*******************************************************************************

**CAUTION**: Prunerr is currently in pre-alpha status and the risk of doing harm to the
media libraries and download clients managed by Servarr is higher than it will be as it
gets more testing.  Bugs in Prunerr may result in, but are not limited to, the following
issues with download client items:

- being deleted before they've met your seeding requirements
- being moved out from under Servarr breaking file imports
- stopping downloading when it shouldn't be stopped
- misidentified as orphans and deleted early

Please do use Prunerr, but use at your own risk and report all issues you encounter with
full details.  Better yet, debug the issue, fix it, and submit a PR.  It's often
impractical to keep a full backup of our media libraries, so set up a small sandbox with
copies of media that can be safely deleted, make sure Prunerr is working smoothly for
you for some time throughout the Servarr/Prunerr lifecycle before using it with your
real library and even then understand the risks.


*******
Summary
*******

The ``$ prunerr`` command is intended to serve as a companion to the `Servarr`_ suite of
applications and services.  It periodically polls the `download clients`_ of `Sonarr`_,
`Radarr`_, etc..  For each client it "prunes" download items by checking disk space
compared to download rate and selectively removing items and deleting item data to
maintain a healthy margin of disk space.  Download items are deleted in an order
determined by a set of rules and criteria that can be defined on a per-indexer basis.
This is mostly useful for `BitTorrent`_ download clients in order to maximize ratio on a
per-indexer/per-tracker basis.

The Servarr state of download items (grabbed, downloading, imported, and/or deleted)
must be reflected in the download client in order to do the above.  Servarr instances
use the ``$ ./bin/prunerr handle ...`` sub-command as a `Servarr Custom Script`_ under
the ``Connect`` Servarr settings to accomplish this.

Prunerr uses and requires a configuration file which defaults to
``~/.config/prunerr.yml``.  See the well-commented sample configuration:
`<./home/.config/prunerr.yml>`_.


*******************
Order of Operations
*******************

Note that polling is required because there is no event we can subscribe to that
reliably determines disk space margin *as* the download clients are downloading.

#. Review download items:

   Apply per-indexer operations to all download items.  Useful, for example, to:
   - adjust priorities
   - remove torrents containing archives (`*.rar`, `*.zip`, `*.tar.gz`, etc.)
   - remove stalled torrents and trigger a search
   - etc.

#. Identify and report orphan files and directories:

   Walk all the top-level directories used by each download client and identify which
   paths don't correspond to a download client item.

#. Identify and report un-managed download items:

   Compare all download client items against those added by each `Servarr`_ application
   to identify those that weren't added by a `Servarr`_ application and are therefor
   un-managed or managed by something else.  Note that these items aren't considered for
   deletion.  Not reported under ``$ prunerr deamon`` to reduce logging noise.

#. Order download items deleted by Servarr according to per-indexer rules:

   Apply the per-indexer/per-tracker rules to each item and use the results to define the
   order in which to delete items as needed for disk space.  See the ``indexers``
   section in `the sample Prunerr configuration file <./home/.config/prunerr.yml>`_ for
   details on how to define these rules.

#. Calculate required disk margin based on download speed:

   Calculate an appropriate margin of disk space to keep free when deciding whether to
   prune download items based the maximum download bandwidth/speed in Mbps and the
   amount of time in seconds at that rate for which download clients should be able to
   continue downloading without exhausting disk space.

#. Remove/delete download client items until margin is reached:

   Per the order from #3, remove one download client item at a time and delete it's
   data, wait until the data can be confirmed as deleted, check disk space again and
   repeat as needed until the margin is reached.

#. Stop downloading if the disk space margin can't be reached

   If the margin can't be reached, report an error and stop the download client from
   downloading any further data.  This is useful to avoid a number of issues that can
   happen if disk space is fully exhausted, including corrupted download client state
   and/or data.


*********************
Servarr Custom Script
*********************

Prunerr reflects the Servarr state of download items in the state of items in the
download client.  This is in keeping with the design principles of Servarr applications
which interpret the external state of download items, media files, etc. rather than rely
on a representation in a DB or some other external persistent storage.  This allows the
user to inspect Prunerr/Servarr state in the native UI for the download client, supports
manual user intervention, and avoids an additional dependency.

Specifically, Prunerr moves the location of download client items as items proceed
through the Servarr workflow: ``./downloads/**`` -> ``./imported/**`` ->
``./deleted/**``.  In order to reflect which individual files have been imported and
where, Prunerr also creates ``./*-ServarrName-import.ln`` symbolic links next to the
download client item as individual files are imported by Servarr instances.  This way,
broken symlinks are an indicator of upgraded files.

Prunerr needs to know which Servarr instance is invoking ``$ prunerr handle`` in order
to use the correct Prunerr configuration.  Unfortunately, Servarr doesn't support
passing any arguments to Custom Scripts.  As such, using Prunerr as a Custom Script
requires a wrapper script that in turn calls ``$ prunerr handle ${servarr_name}``.  This
wrapper script is what should be used in the ``Path`` field of the Servarr Custom Script
settings. See `<./home/.local/bin/prunerr-sonarr-handle>`_ and
`<./home/.local/bin/prunerr-radarr-handle>`_ for examples.

If the Servarr instance is running in a container, Servarr Custom Scripts must be
executable inside the same container as the Servarr instance.  Since Prunerr does not
support `Python 2.x`_, this means the `linuxserver.io`_ containers are incompatible with
Prunerr.  The `hotio`_ containers are similarly well maintained and do include `Python
3.x`_ so those images *are* compatible with Prunerr.  This also means that Prunerr must
be installed into the container.  See `<./docker-compose.yml>`_ for examples of how to
stitch all this together in a deployment in containers.

Prunerr also provides a ``$ ./bin/prunerr sync`` sub-command to introspect the item
history from Servarr instances and apply any appropriate state that can be determined
from the Servarr history to the download client items.  This sub-command can be used to
get any existing download client items in sync as if they had been processed by the
``$ prunerr handle ...`` and ``$ prunerr exec`` subcommands.


****************
Other Operations
****************

The ``$ prunerr`` command can also be used to perform other operations outside of the
main polling loop above, such as CLI management commands and responding to events in the
system such as events from download clients and/or `Servarr`_ applications.

- Set per-indexer/per-tracker priority for items in download clients


****
TODO
****

The following are known issues with Prunerr or features that are particularly desirable
to implement in Prunerr.  IOW, contributions are particularly welcome for the following:

- Support download clients on different file-systems, copy completed items:

  There is existing support for copying finished torrents via an arbitrary command, but
  it's currently unused and thus untested and it's very likely that there are
  regressions that need fixing.

  This also involves changing ``$ prunerr daemon`` behavior such that it also considers
  successfully *copied* items as candidates for deletions, not just items whose imported
  files have been deleted by Servarr, such as when upgrading.

- Convert from a Servarr Custom Script to a WebHook:

  This is definitely the better way to do this and addresses a number of issues.

- Send a notification when no download item can be deleted and downloading is paused:

  Perhaps we can use the Servarr "Connect" API?

- **TESTING**!!!!!

  I am embarrassed by this "software".  It grew from ad-hoc maintenance scripts and I
  know that much of the edge case handling in this code is still needed so I'm not
  convinced starting from scratch and running into those edge cases again one-by-one
  would actually result in a net savings of effort.  It's still very much lacking in
  software best practices.  Testing would the best start and would point the direction
  to the best places to start refactoring and cleaning up.

- Support other download client software, not just `Transmission`_:

  This would almost certainly require discussion before implementing, because how this
  is down will be important for maintainability.  So open an issue and start the
  discussion before you start implementing lest your work go to waste.  Currently,
  Prunerr is way to tightly coupled with Transmission and the `Python RPC client
  library`_ used to interface with it.  I suspect the best way to abstract it will be to
  use that client library as a de facto abstract interface and then wrap other client
  libraries to fulfill that interface, but that's one of the things to discuss.

  It's also worth noting that the reason Transmission is the first supported download
  client is because `it seems to be the best`_ at `managing large numbers of torrents
  efficiently`_.  This is the most important download client quality given that the
  primary purpose of Prunerr is to perma-seed whole media libraries and the number of
  managed torrents will grow over time.

- ``$ git grep -i -e todo``:

  The above are the most important improvements that Prunerr definitely needs.  See ``#
  TODO: ...`` comments throughout the source for other smaller, potential improvements.


.. _`Python 3.x`: https://docs.python.org/3/
.. _`Python 2.x`: https://www.python.org/doc/sunset-python-2/

.. _`BitTorrent`: https://en.wikipedia.org/wiki/BitTorrent
.. _`Transmission`: https://transmissionbt.com/
.. _`Python RPC client library`: https://transmission-rpc.readthedocs.io/en/v3.2.6/
.. _`it seems to be the best`: https://www.reddit.com/r/DataHoarder/comments/3ve1oz/torrent_client_that_can_handle_lots_of_torrents/
.. _`managing large numbers of torrents efficiently`: https://www.reddit.com/r/trackers/comments/3hiey5/does_anyone_here_seed_large_amounts_10000_of/

.. _`Servarr`: https://wiki.servarr.com
.. _`Radarr`: https://wiki.servarr.com/en/radarr
.. _`Sonarr`: https://wiki.servarr.com/en/sonarr
.. _`download clients`: https://wiki.servarr.com/radarr/settings#download-clients

.. _`linuxserver.io`: https://docs.linuxserver.io/images/docker-radarr
.. _`hotio`: https://hotio.dev/containers/radarr/
