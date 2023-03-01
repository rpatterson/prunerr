###########################################################################
Seeking Contributions
###########################################################################

The following are known issues with Prunerr or features that are particularly desirable
to implement in Prunerr.  IOW, contributions are particularly welcome for the following:


********
Required
********


*************
High Priority
*************

#. Operations reference, perhaps done dynamically from the CLI help using operation
   method docstrings.

#. Any documentation improvements!

   Documentation benefits perhaps most from the attention of fresh eyes.  If you find
   anything confusing, please ask for clarification and once you understand what you
   didn't before, please do contribute changes to the documentation to spare future
   users the same confusion.

#. Find a good way to review download items that are now only partially hard
   linked. IOW, when only some episodes from one download item have replaced only some
   episodes from another.  Maybe extend the existing operations support to write CSV
   report files?

#. Send a notification when no download item can be deleted and downloading is paused:

   Perhaps we can use the Servarr "Connect" API?

************
Nice to Have
************

#. Improve configure-ability, particularly the various download client paths:

   Currently, Prunerr strongly depends on using the ``.../incomplete/``,
   ``.../downloads/``, ``.../imported/``,  and ``.../deleted/`` paths.  In theory, these
   paths are all configurable, but that's untested.

#. Unit tests

   The current tests are probably most accurately described as integration tests.  Any
   tests that cover discreet units are welcome.

#. Resurrect the ``rename`` command.  See the ``feat(rename): Remove series title rename
   support`` commit that removed it.

#. Support other download client software, not just `Transmission`_:

   This would almost certainly require discussion before implementing, because how this
   is done would be important for maintainability.  So open an issue and start the
   discussion before you start implementing lest your work go to waste.  Currently,
   Prunerr is way to tightly coupled with Transmission and the `Python RPC client
   library`_ used to interface with it.  I suspect the best way to abstract it will be
   to use that client library as a de facto abstract interface and then wrap other
   client libraries to fulfill that interface, but that's one of the things to discuss.

   It's also worth noting that the reason Transmission is the first supported download
   client is because `it seems to be the best`_ at `managing large numbers of torrents
   efficiently`_.  This is the most important download client quality given that the
   primary purpose of Prunerr is to perma-seed whole media libraries and the number of
   managed torrents will grow over time.

#. ``$ git grep -i -e todo``:

   The above are the most important improvements that Prunerr definitely needs.  See ``#
   TODO: ...`` comments throughout the source for other smaller, potential improvements.

#. Fix items with character mapping (Samba) treated as orphans.

#. Items deleted from download client outside of Prunerr being re-added.

#. Limit total number of torrents by deleting imported public torrents

   One private tracker kept reporting that Transmission is not seeding torrents I see as
   seeding in the UI.  I paused all seeding public torrents, amounting to ~1/2 of ~1500
   total torrents.  Then I started resuming torrents until the tracker started reported
   those torrents as seeding again, but I forgot to write down the numbers.  At this
   moment the private tracker is reporting torrents as not seeding again and current
   numbers are:

     - All = 1463
     - Downloading = 62
     - Seeding = 1193
     - Paused = 208
     - Complete = 1398
     - Incomplete = 65
     - Active = 234

   The private tracker now reports all torrents as seeding:

     - All = 1464
     - Downloading = 64
     - Seeding = 1164
     - Paused = 236
     - Complete = 1398
     - Incomplete = 66
     - Active = 255

   Seems like maybe the threshold is ~1200 unpaused torrents
   Still reporting seeding:

     - All = 1465
     - Downloading = 59
     - Seeding = 1170
     - Paused = 236
     - Complete = 1404
     - Incomplete = 61
     - Active = 259

   It occurs to me that the issue could be with some specific subset of torrents rather
   than the number of torrents.  So I resumed all torrents that were already paused
   before the last round of pausing torrents.

     - All = 1465
     - Downloading = 59
     - Seeding = 1375
     - Paused = 31
     - Complete = 1404
     - Incomplete = 61
     - Active = 302

   The tracker still reports all items seeding so this may be specific to some subset of
   torrents.  It may be that it's related to particularly active torrents.

   Tracker still reports all seeding even with all torrents un-paused:

     - All = 1467
     - Downloading = 59
     - Seeding = 1408
     - Paused =
     - Complete = 1408
     - Incomplete = 59
     - Active = 392


.. _`Transmission`: https://transmissionbt.com/
.. _`Python RPC client library`: https://transmission-rpc.readthedocs.io/en/v3.2.6/
.. _`it seems to be the best`: https://www.reddit.com/r/DataHoarder/comments/3ve1oz/torrent_client_that_can_handle_lots_of_torrents/
.. _`managing large numbers of torrents efficiently`: https://www.reddit.com/r/trackers/comments/3hiey5/does_anyone_here_seed_large_amounts_10000_of/
