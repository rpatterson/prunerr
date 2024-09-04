.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Most wanted contributions
########################################################################################

Known bugs and wanted features.


****************************************************************************************
Required
****************************************************************************************

#. Revert Docker compose project to the latest Transmission image when `the upstream
   PUID regression
   <https://github.com/linuxserver/docker-transmission/issues/284#issue-2451398884>`_
   has been fixed.

#. Use YAML anchors and merge keys to demonstrate how to share configuration between
   indexers?

#. Move critical disk space container shutdown into a ``periodic`` script.

#. Extend critical disk space container shutdown to the Transmission data filesystem.

#. Take ``done-date`` from Servarr when missing or 0 in Transmission.

#. Add torrent date handling to the ``export`` sub-command. Take the ``grabbed`` history
   record dates for the ``added-date`` and the ``downloadFolderImported`` record dates
   for the ``done-date`` and `set them in the Transmission '/config/resume/*.resume'
   files
   <https://github.com/transmission/transmission/issues/4314#issuecomment-1336485761>`_
   if those dates are older than the current.


****************************************************************************************
High priority
****************************************************************************************

#. Add a review to exclude BluRay/DVD full disc rips.

#. Deselect unimported files before deciding whether to delete?

#. When removing download items from the client while running the ``$ prunerr
   free-space`` sub-command, avoid a heavily loaded client blocking deleting items by
   sending the ``remove_torrent()`` `request asynchronously
   <https://www.python-httpx.org/async/>`_.

#. Link the top-level docs for each sub-command into their runner API docs.

#. Investigate Transmission "Labels". They're not visible in the Transmission Remote GTK
   GUI but they are visible in the web UI. Should we replace the use of directories with
   labels?

#. Well documented configuration snippets demonstrating all important use cases.

#. Operations reference, perhaps done dynamically from the CLI help using operation
   method docstrings.

#. Any documentation improvements:

   Docs benefit most from fresh eyes. If you find anything confusing, ask for help. When
   you understand better, contribute changes to the docs to help others.

#. Find a good way to review download items that are now only partially hard
   linked. IOW, when only some episodes from one download item have replaced only some
   episodes from another. Maybe extend the existing operations support to write CSV
   report files?

#. Send a notification when disk space is low and no download item can be deleted:

   Perhaps we can use the Servarr "Connect" API?

#. Refactor per-indexer configuration to support sharing between indexers?


****************************************************************************************
Nice to have
****************************************************************************************

#. Also import `extras and such
   <https://jellyfin.org/docs/general/server/media/movies/#movie-extras>`_ that Servarr
   doesn't support.

#. Support selecting only one series or movie for the ``export`` sub-command.

#. Implement ``__eq__`` or better and audit other "dunder" methods to implement. Use the
   normalized ``self.config["url"]`` for servarr and download client instances.

#. Improve configure-ability, particularly the various download client paths:

   Currently, Prunerr hard-codes the ``.../incomplete/``, ``.../downloads/``, and
   ``.../seeding/`` paths.

#. Report multi-season items that are only partially imported.

#. Unit tests

   The current tests are probably most accurately described as integration tests. Any
   tests that cover discreet units are welcome.

#. Resurrect the ``rename`` command. See the ``feat(rename): Remove series title rename
   support`` commit that removed it.

#. Support other download client software, not only `Transmission
   <https://transmissionbt.com/>`_:

   Should be implemented external to Prunerr. That could be a Python library that
   provides a single API that can talk to the APIs of different Transmission clients.
   It could also be an external service that Prunerr can talk to that know how manage
   different Transmission clients. For example, if Sonarr/Radarr added a complete API to
   download clients, then Prunerr could switch to that.

   It's also worth noting that the reason Transmission is the first supported download
   client is because `it seems to be the best
   <https://www.reddit.com/r/DataHoarder/comments/3ve1oz/torrent_client_that_can_handle_lots_of_torrents/?rdt=42633>`_
   at `managing large numbers of torrents efficiently
   <https://www.reddit.com/r/trackers/comments/3hiey5/does_anyone_here_seed_large_amounts_10000_of/?rdt=37283>`_.
   This is the most important download client quality given that the primary purpose of
   Prunerr is to perma-seed whole media libraries and the number of managed torrents
   will grow over time.

#. ``$ git grep -i -e todo``:

   The above are the most important improvements that Prunerr definitely needs. See ``#
   TODO: ...`` comments throughout the source for other smaller, potential improvements.

#. Fix items with character mapping (Samba) treated as orphans.

#. Use real item data from the actual tracker:

   Currently, we use ``seconds_downloading`` to estimate seeding time and in turn
   approximate tracker "hit 'n run" (HnR) rules. It turns out Transmission provides no
   reliable way to calculate seeding time and even if it did, that's still not the same
   quantity as seen by the tracker. This also turns out to be consequential in real
   world usage. Not often, but regularly, I observe Prunerr deleting items that then
   show up as an HnR in the tracker even though my ``seconds_downloading`` includes a
   full day's worth of margin.

   To this end, and likely others, it would be nice to have a way to access real tracker
   data in the Prunerr operations configurations. This should be implemented in an
   external library or service and used in Prunerr, like multiple download client
   support above. For widely used tracker software, e.g. Gazelle, it may be acceptable
   to have less configurable pre-sets, but it should definitely include a highly
   configurable approach as well given the prevalence of patched forks, customized UI,
   etc.. It should include generalized support for configuring how to scrape data from
   HTML, probably using XPaths.

#. Re-enable the prose linters and address all failures.

#. :Tests: Add test cases for the test coverage holes in the ``$ prunerr export``
           sub-command.
