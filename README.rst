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
you for some time throughout the Servarr/Prunerr life-cycle before using it with your
real library and even then understand the risks.


*******
Summary
*******

The ``$ prunerr`` command is intended to serve as a companion to the `Servarr`_ suite of
applications and services and the `Transmission BitTorrent client`_.  It periodically
polls the `download clients`_ of `Sonarr`_, `Radarr`_, etc..  For each client it
"prunes" download items by checking disk space compared to download rate and selectively
removing items and deleting item data to maintain a healthy margin of disk space.
Download items are deleted in an order determined by a set of rules and criteria that
can be defined on a per-indexer basis.  This is mostly useful to maximize ratio on a
per-indexer/per-tracker basis.  IOW, Prunerr "perma-seeds" your Servarr library.

As Servarr acts on completed download items, be that importing files from them, ignoring
them, deleting them from the queue, etc., Prunerr moves those items from the Servarr
download client's ``Directory`` to a parallel ``*/seeding/*`` directory.  Then when
deleting download items to free space, Prunerr only considers items under that
directory.  This has the added benefit of reflecting which items have been acted on by
Servarr in the download client.

Prunerr uses and requires a configuration file which defaults to
``~/.config/prunerr.yml``.  See the well-commented sample configuration:
`<./src/prunerr/home/.config/prunerr.yml>`_.


***********
Quick Start
***********

TODO


*******************
Order of Operations
*******************

Note that polling is required because there is no event we can subscribe to that
reliably determines disk space margin *as* the download clients are downloading.

#. Move Servarr download item that have been acted on to the ``*/seeding/*`` directory.

#. Review download items:

   Apply per-indexer operations to all download items.  Useful, for example, to:
   - adjust priorities
   - remove torrents containing archives (`*.rar`, `*.zip`, `*.tar.gz`, etc.)
   - remove stalled torrents and trigger a search
   - etc.

TODO: Review and update below

#. Identify and report orphan files and directories:

   Walk all the top-level directories used by each download client and identify which
   paths don't correspond to a download client item.

#. Identify and report un-managed download items:

   Compare all download client items against those added by each `Servarr`_ application
   to identify those that weren't added by a `Servarr`_ application and are therefor
   un-managed or managed by something else.  Note that these items aren't considered for
   deletion.  Not reported under ``$ prunerr daemon`` to reduce logging noise.

#. Order download items deleted by Servarr according to per-indexer rules:

   Apply the per-indexer/per-tracker rules to each item and use the results to define
   the order in which to delete items as needed for disk space.  See the ``indexers``
   section in `the sample Prunerr configuration file
   <./src/prunerr/home/.config/prunerr.yml>`_ for details on how to define these rules.

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

- Update docs after rewrite

- Find a good way to review download items that are now only partially hard linked.
  IOW, when only some episodes from one download item have replaced only some episodes
  from another.  Maybe a partial/mixed status?

- Send a notification when no download item can be deleted and downloading is paused:

  Perhaps we can use the Servarr "Connect" API?

- Improve configure-ability, particularly the various download client paths:

  Currently, Prunerr strongly depends on using the ``.../incomplete/``,
  ``.../downloads/``, ``.../imported/``,  and ``.../deleted/`` paths.  In theory, these
  paths are all configurable, but that's untested.

- 100% test coverage

- Unit tests

  The current tests are probably most accurately described as integration tests.  Any
  tests that cover discreet units are welcome.

- Resurrect the ``rename`` command.  See the ``feat(rename): Remove series title rename
  support`` commit that removed it.

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

- Fix items with character mapping (Samba) treated as orphans.

- Document that we prioritize first for free storage space then for seeding.

- Items deleted from download client outside of Prunerr being re-added.


.. _`Transmission`: https://transmissionbt.com/
.. _`Transmission BitTorrent client`: `Transmission`_
.. _`Python RPC client library`: https://transmission-rpc.readthedocs.io/en/v3.2.6/
.. _`it seems to be the best`: https://www.reddit.com/r/DataHoarder/comments/3ve1oz/torrent_client_that_can_handle_lots_of_torrents/
.. _`managing large numbers of torrents efficiently`: https://www.reddit.com/r/trackers/comments/3hiey5/does_anyone_here_seed_large_amounts_10000_of/

.. _`Servarr`: https://wiki.servarr.com
.. _`Radarr`: https://wiki.servarr.com/en/radarr
.. _`Sonarr`: https://wiki.servarr.com/en/sonarr
.. _`download clients`: https://wiki.servarr.com/radarr/settings#download-clients
