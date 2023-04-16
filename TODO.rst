########################################################################################
Seeking Contributions
########################################################################################

The following are known issues with Prunerr or features that are particularly desirable
to implement in Prunerr.  IOW, contributions are particularly welcome for the following:


****************************************************************************************
Required
****************************************************************************************


****************************************************************************************
High Priority
****************************************************************************************

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

****************************************************************************************
Nice to Have
****************************************************************************************

#. Improve configure-ability, particularly the various download client paths:

   Currently, Prunerr hard-codes the ``.../incomplete/``, ``.../downloads/``, and
   ``.../seeding/`` paths.

#. Unit tests

   The current tests are probably most accurately described as integration tests.  Any
   tests that cover discreet units are welcome.

#. Resurrect the ``rename`` command.  See the ``feat(rename): Remove series title rename
   support`` commit that removed it.

#. Support other download client software, not just `Transmission`_:

   Should be implemented external to Prunerr.  That could be a Python library that
   provides a single API that can talk to the APIs of different Transmission clients.
   It could also be an external service that Prunerr can talk to that know how manage
   different Transmission clients.  For example, if Sonarr/Radarr added a more complete
   API to download clients, then Prunerr could switch to that.

   It's also worth noting that the reason Transmission is the first supported download
   client is because `it seems to be the best`_ at `managing large numbers of torrents
   efficiently`_.  This is the most important download client quality given that the
   primary purpose of Prunerr is to perma-seed whole media libraries and the number of
   managed torrents will grow over time.

#. ``$ git grep -i -e todo``:

   The above are the most important improvements that Prunerr definitely needs.  See ``#
   TODO: ...`` comments throughout the source for other smaller, potential improvements.

#. Fix items with character mapping (Samba) treated as orphans.


.. _`Transmission`: https://transmissionbt.com/
.. _`it seems to be the best`: https://www.reddit.com/r/DataHoarder/comments/3ve1oz/torrent_client_that_can_handle_lots_of_torrents/
.. _`managing large numbers of torrents efficiently`: https://www.reddit.com/r/trackers/comments/3hiey5/does_anyone_here_seed_large_amounts_10000_of/
