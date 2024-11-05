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

#. :Docker:

    Revert Docker compose project to the latest Transmission image when `the upstream
    PUID regression
    <https://github.com/linuxserver/docker-transmission/issues/284#issue-2451398884>`_
    has been fixed.

#. :Documentation:

    Verify the `CI docs build <https://readthedocs.org/projects/prunerr/>`_.

#. :Documentation:

    Move as much as appropriate of ``./README.rst`` into separate ``./docs/*.rst`` files
    after the CI docs build is working.


****************************************************************************************
High priority
****************************************************************************************

#. :Fail:

   Open Servarr issues about marking releases as failed broken search. See the comment
   in the ``un-regsitered:`` operation configuration.

#. :Operations:

    Extract indexer priorities from Servarr.

#. :Notify:

    Move ``ntfy`` logging handler into a PR or a separate package.

#. :Queued:

    Identify download items that will only be partially imported, for example
    multi-season packs. Send a notification and move to ``**/importing/*``.

#. :Free-space:

    Avoid deleting large files blocking Prunerr. Delete file asynchronously but be
    careful that files that are yet to be deleted don't affect subsequent actions and
    daemon loops.

#. :Transmission:

    Avoid a heavily loaded download client blocking Prunerr by sending Transmission RPC
    `requests asynchronously <https://www.python-httpx.org/async/>`_.

#. :Operations:

    Audit operation actions that call ``torrent.update()`` and see if it's possible to
    avoid those RPC API calls.

#. :Queued:

    Add a ``queued:`` operation to block-list BluRay/DVD full disc rips.

#. :Documentation:

    Link the top-level docs for each sub-command into their runner API docs.

#. :Documentation:

    Link the top-level operations documentation to the ``prunerr.downloaditem`` API
    docs for the download item and download item file properties. This may require
    refactoring into base classes and/or separate modules to make the result more
    approachable. Add explanations to the item and file class docstrings including
    links to the Transmission RPC documentation for what fields are available in the
    item class and to the Python ``transmission_rpc.lib_types.File`` documentation
    for what attributes are available.

#. :Documentation:

    Build example config into the built docs for stable line number links.

#. :Documentation:

    Does Sphinx provide any way to render docs from the comments in the example
    config?

    - `moderncmakedomain <https://github.com/scikit-build/moderncmakedomain>`_
    - `yamldoc <https://chrisbcole.me/yamldoc/sphinx/>`_

#. :Transmission:

    Investigate Transmission "Labels". They're not visible in the Transmission Remote
    GTK GUI but they are visible in the web UI. Should we replace the use of directories
    with labels?

#. :Documentation:

    Any documentation improvements:

    Docs benefit most from fresh eyes. If you find anything confusing, ask for
    help. When you understand better, contribute changes to the docs to help others.

#. :Operations:

    See if Home Assistant is interested in breaking out their set of Jinja filters,
    tests, etc., into a Jinja extension. Selected Home Assistant because it's Jinja
    extensions are in wide use by similar types of users as Prunerr's intended users,
    particularly technological enthusiast non-developers, and already has documentation
    to that end.


****************************************************************************************
Nice to have
****************************************************************************************

#. :Operations:

    Add an interactive prompt mode where the user is prompted for ``y/n`` every time
    Prunerr would make a change. Make the prompt a sub-class of ``pdb.Pdb`` for
    inspecting the context with additional commands for proceeding or skipping the given
    action.

#. :Seeding:

    Also import `extras and such
    <https://jellyfin.org/docs/general/server/media/movies/#movie-extras>`_ that Servarr
    doesn't support.

#. :Export:

    Support selecting only one series or movie for the ``export`` sub-command.

#. :Operations:

    Add a ``csv:`` action to write ``*.csv`` files with a row for each included download
    item. The keys under the ``csv:`` key should be column labels and the values should
    be templates to render cell values for each item.

#. :Style:

    Implement ``__eq__`` or better and audit other "dunder" methods to implement. Use
    the normalized ``self.config["url"]`` for servarr and download client instances.

#. :Configuration:

    Improve configure-ability, particularly the various download client paths:

    Currently, Prunerr hard-codes the ``.../incomplete/``, ``.../downloads/``, and
    ``.../seeding/`` paths.

#. :Tests:

    Unit tests

    The current tests are probably most accurately described as integration tests. Any
    tests that cover discreet units are welcome.

#. :Rename:

    Resurrect the ``rename`` command. See the ``feat(rename): Remove series title rename
    support`` commit that removed it.

#. :Transmission:

    Support other download client software, not only `Transmission
    <https://transmissionbt.com/>`_:

    Should be implemented external to Prunerr. That could be a Python library that
    provides a single API that can talk to the APIs of different Transmission clients.
    It could also be an external service that Prunerr can talk to that know how manage
    different Transmission clients. For example, if Sonarr/Radarr added a complete API
    to download clients, then Prunerr could switch to that.

    It's also worth noting that the reason Transmission is the first supported download
    client is because `it seems to be the best
    <https://www.reddit.com/r/DataHoarder/comments/3ve1oz/torrent_client_that_can_handle_lots_of_torrents/?rdt=42633>`_
    at `managing large numbers of torrents efficiently
    <https://www.reddit.com/r/trackers/comments/3hiey5/does_anyone_here_seed_large_amounts_10000_of/?rdt=37283>`_.
    This is the most important download client quality given that the primary purpose of
    Prunerr is to perma-seed whole media libraries and the number of managed torrents
    will grow over time.

#. :TODO:

    ``$ git grep -i -e todo``:

    The above are the most important improvements that Prunerr definitely needs. See ``#
    TODO: ...`` comments throughout the source for other smaller, potential
    improvements.

#. :Orphans:

    Fix items with character mapping (Samba) treated as orphans.

#. :Indexers:

    Use real item data from the actual tracker:

    Currently, we use ``seconds_downloading`` to estimate seeding time and in turn
    approximate tracker "hit 'n run" (HnR) rules. It turns out Transmission provides no
    reliable way to calculate seeding time and even if it did, that's still not the same
    quantity as seen by the tracker. This also turns out to be consequential in real
    world usage. Not often, but regularly, I observe Prunerr deleting items that then
    show up as an HnR in the tracker even though my ``seconds_downloading`` includes a
    full day's worth of margin.

    To this end, and likely others, it would be nice to have a way to access real
    tracker data in the Prunerr operations configurations. This should be implemented in
    an external library or service and used in Prunerr, like multiple download client
    support above. For widely used tracker software, e.g. Gazelle, it may be acceptable
    to have less configurable pre-sets, but it should definitely include a highly
    configurable approach as well given the prevalence of patched forks, customized UI,
    etc.. It should include generalized support for configuring how to scrape data from
    HTML, probably using XPaths.

 #. :Export:

    Servarr metadata plugins may write ``**/*.nfo`` files but some configurations may
    import and preserve download item files. Map Servarr metadata plugin implementation
    types to the file extensions they manage, request the metadata plugins from the
    Servarr API, and only exclude files with those extensions in
    ``prunerr.commands.export.ExportServarrRootItem.link_imported_files()`` if the
    corresponding metadata plugin is enabled.

#. :Tests:

    Add test cases for the ignored test coverage holes::

        $ git grep -i -e 'pragma: no cover' -- '*.py'

#. :Lint:

    Resolve ignored linter failures::

        $ git grep -i -e 'alex disable hooks|hadolint ignore\
        |pylint: disable|type: ignore|noqa|nosec' -- '*.py'

#. :Lint:

    Re-enable the prose linters and address all failures.

#. :Lint:

    Add container type annotations, for example ``foo: dict[str, int]``, once Python 3.8
    BBB support is dropped.

#. :Style:

    Rename ``dir_*`` to ``lib_*`` throughout the code base.
