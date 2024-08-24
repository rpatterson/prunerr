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

#. Add torrent date handling to the ``export`` sub-command. Take the ``grabbed`` history
   record dates for the ``added-date`` and the ``downloadFolderImported`` record dates
   for the ``done-date`` and `set them in the Transmission '/config/resume/*.resume'
   files
   <https://github.com/transmission/transmission/issues/4314#issuecomment-1336485761>`_
   if those dates are older than the current.


****************************************************************************************
High priority
****************************************************************************************

#. :notify: Move ``ntfy`` logging handler into a PR or a separate package.

#. Report which seeding items will be deleted when space runs low so the user can
   intervene before if possible. Also send notifications once we've decided on a way to
   do that.

#. Move deleting unregistered items to a review.

#. Move deleting orphans to a separate sub-command.

#. Deselect unimported files before deciding whether to delete?

#. When removing download items from the client while running the ``$ prunerr
   free-space`` sub-command, avoid a heavily loaded client blocking deleting items by
   sending the ``remove_torrent()`` `request asynchronously
   <https://www.python-httpx.org/async/>`_.

#. Allow grouping indexers/trackers. Refactor operations configuration to be by
   arbitrary named groups that include multiple indexers/trackers.

#. Add a review to exclude BluRay/DVD full disc rips.

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

#. Send a notification when disk space is low and no download item can be deleted. The
   Servarr API doesn't provide an endpoint for sending notifications that I can find, so
   we'll need to adopt a tool or framework. I already use and love `ntfy
   <https://ntfy.readthedocs.io/en/latest/ntfy.html#ntfy.notify>`_ so might as well use
   that.

#. Refactor per-indexer configuration to support sharing between indexers?


****************************************************************************************
Nice to have
****************************************************************************************

#. Add an interactive prompt mode where the user is prompted for ``y/n`` every time
   Prunerr would make a change. Make the prompt a sub-class of ``pdb.Pdb`` for
   inspecting the context with additional commands for proceeding or skipping the given
   action.

#. Maybe refactor everything to be centered around arbitrary phases and groups of
   operations. Move what Prunerr does in the ``review`` and ``free-space`` sub-commands
   and the order of operations in general into groups of operations.

#. Also import `extras and such
   <https://jellyfin.org/docs/general/server/media/movies/#movie-extras>`_ that Servarr
   doesn't support.

#. Support selecting only one series or movie for the ``export`` sub-command.

#. Extend the existing operations support to write CSV report files.

#. Implement ``__eq__`` or better and audit other "dunder" methods to implement. Use the
   normalized ``self.config["url"]`` for servarr and download client instances.

#. Improve configure-ability, particularly the various download client paths:

   Currently, Prunerr hard-codes the ``.../incomplete/``, ``.../downloads/``, and
   ``.../seeding/`` paths.

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

#. :Tests: Add test cases for the ignored test coverage holes::

             $ git grep -i -e 'pragma: no cover' -- '*.py'

#. :Lint: Resolve ignored linter failures::

            $ git grep -i -e 'alex disable hooks|hadolint ignore|pylint: disable|type: ignore' -- '*.py'

#. :Lint: Re-enable the prose linters and address all failures.
