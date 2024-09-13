.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Prunerr
########################################################################################
Perma-seed Servarr media libraries
****************************************************************************************

.. list-table::
   :class: borderless align-right

   * - .. figure:: https://img.shields.io/pypi/v/prunerr.svg?logo=pypi&label=PyPI&logoColor=gold
          :alt: PyPI latest release version
          :target: https://pypi.org/project/prunerr/
       .. figure:: https://img.shields.io/pypi/pyversions/prunerr.svg?logo=python&label=Python&logoColor=gold
          :alt: PyPI Python versions
          :target: https://pypi.org/project/prunerr/
       .. figure:: https://img.shields.io/badge/code%20style-black-000000.svg
          :alt: Python code style
          :target: https://github.com/psf/black
       .. figure:: https://api.reuse.software/badge/gitlab.com/rpatterson/prunerr
          :alt: Reuse license status
          :target: https://api.reuse.software/info/gitlab.com/rpatterson/prunerr

     - .. figure:: https://gitlab.com/rpatterson/prunerr/-/badges/release.svg
          :alt: GitLab latest release
          :target: https://gitlab.com/rpatterson/prunerr/-/releases
       .. figure:: https://gitlab.com/rpatterson/prunerr/badges/main/pipeline.svg
          :alt: GitLab CI/CD pipeline status
          :target: https://gitlab.com/rpatterson/prunerr/-/commits/main
       .. figure:: https://gitlab.com/rpatterson/prunerr/badges/main/coverage.svg
          :alt: GitLab coverage report
          :target: https://gitlab.com/rpatterson/prunerr/-/commits/main
       .. figure:: https://img.shields.io/gitlab/stars/rpatterson/prunerr?gitlab_url=https%3A%2F%2Fgitlab.com&logo=gitlab
          :alt: GitLab repository stars
          :target: https://gitlab.com/rpatterson/prunerr

     - .. figure:: https://img.shields.io/github/v/release/rpatterson/prunerr?logo=github
          :alt: GitHub release (latest SemVer)
          :target: https://github.com/rpatterson/prunerr/releases
       .. figure:: https://github.com/rpatterson/prunerr/actions/workflows/build-test.yml/badge.svg
          :alt: GitHub Actions status
          :target: https://github.com/rpatterson/prunerr/actions/workflows/build-test.yml
       .. figure:: https://codecov.io/github/rpatterson/prunerr/branch/main/graph/badge.svg?token=GNKVQ8VYOU
          :alt: Codecov test coverage
          :target: https://app.codecov.io/github/rpatterson/prunerr
       .. figure:: https://img.shields.io/github/stars/rpatterson/prunerr?logo=github
          :alt: GitHub repository stars
          :target: https://github.com/rpatterson/prunerr/

     - .. figure:: https://img.shields.io/docker/v/merpatterson/prunerr?sort=semver&logo=docker
          :alt: Docker Hub image version
          :target: https://hub.docker.com/r/merpatterson/prunerr
       .. figure:: https://img.shields.io/docker/pulls/merpatterson/prunerr?logo=docker
          :alt: Docker Hub image pulls count
          :target: https://hub.docker.com/r/merpatterson/prunerr
       .. figure:: https://img.shields.io/docker/stars/merpatterson/prunerr?logo=docker
          :alt: Docker Hub stars
          :target: https://hub.docker.com/r/merpatterson/prunerr
       .. figure:: https://img.shields.io/docker/image-size/merpatterson/prunerr?logo=docker
          :alt: Docker Hub image size
          :target: https://hub.docker.com/r/merpatterson/prunerr

     - .. figure:: https://img.shields.io/keybase/pgp/rpatterson?logo=keybase
          :alt: KeyBase Pretty Good Privacy (PGP) key ID
          :target: https://keybase.io/rpatterson
       .. figure:: https://img.shields.io/github/followers/rpatterson?style=social
          :alt: GitHub followers count
          :target: https://github.com/rpatterson
       .. figure:: https://img.shields.io/liberapay/receives/rpatterson.svg?logo=liberapay
          :alt: LiberaPay donated per week
          :target: https://liberapay.com/rpatterson/donate
       .. figure:: https://img.shields.io/liberapay/patrons/rpatterson.svg?logo=liberapay
          :alt: LiberaPay patrons count
          :target: https://liberapay.com/rpatterson/donate


TL;DR: Perma-seeding of whole Servarr libraries optimized for per-tracker ratio.

- Delete torrents/items `only as disk space gets low
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L36-50>`_.
- Don't delete `currently imported items
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L270-273>`_.
  IOW, only delete upgraded items.
- Don't delete `private items that haven't met seeding requirements
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L275-290>`_.
- Delete `public items first
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L318-320>`_.
- Delete private items in `an order to maximize tracker ratio and/or bonuses
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L335-351>`_.
- Delete `stalled items
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L148-162>`_
  , and `items containing archives such as *.rar
  releases
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L113-119>`_
  and `blacklist them
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L139-140>`_,
  AKA mark them as failed, in Servarr.
- And more...

.. include-end-before
.. contents:: Table of Contents
.. include-start-after


****************************************************************************************
Summary
****************************************************************************************

Seed Servarr download client torrents/items as long as possible only deleting them as
necessary as disk space gets low, hence the name based on "to prune". Which download
items are considered eligible for deletion is configured by the user. The common case is
that download items that are currently imported are not considered for deletion.
Neither are items from private trackers/indexers that have been upgraded or otherwise
deleted from the library but haven't met the indexers seeding requirements. The order in
which download items are deleted is determined according to rules configured by the
user. The common case is to delete items from public indexers first and among those to
delete the items with the highest ratio first to preserve the health of the community by
seeding less popular items longer. Next delete items from private indexers by configured
indexer priority and within the items for a given indexer to delete items in an order to
maximize ratio and/or seeding rewards.

Other configured operations may be applied as well. For example:

- Verify and resume corrupt items
- Increase bandwidth priority for items from private indexers
- Decrease bandwidth priority for items from public indexers
- Remove and blacklist download items containing archives (``*.rar``, ``*.zip``,
  ``*.tar.gz``, etc.) which can't be perma-seeded
- Remove and blacklist stalled download items
- etc.

The ``$ prunerr`` command is intended to serve as a companion to the `Servarr`_ suite of
applications and services and the `Transmission BitTorrent client`_. It periodically
polls the `download clients`_ of `Sonarr`_, `Radarr`_, etc. and applies the configured
operations to the download items in each of those download clients. It can also be run
independently of any Servarr instances to optimize seeding for download items added by
other means, e.g. `FlexGet`_.

See the `Usage`_ section below for full details.


****************************************************************************************
Installation
****************************************************************************************

Install locally or use the Docker container image:

Local Installation
========================================================================================

Install by using any tool for installing standard Python 3 distributions such as
`pip`_::

  $ pip3 install --user prunerr

Optional shell prompt tab completion is available by using `argcomplete`_.

Docker Container Image
========================================================================================

The recommended way to use the container image is by using `Docker Compose`_. See `the
example ./docker-compose.yml file`_. Write your configuration and run the container::

  $ docker compose up

You can also use the image directly. Pull `the Docker image`_. Use it to create and run
a container::

  $ docker pull "registry.gitlab.com/rpatterson/prunerr"
  $ docker run --rm -it "registry.gitlab.com/rpatterson/prunerr" ...

Use image variant tags to control when the image updates. Releases publish tags for the
branch and for major and minor versions. For example, to keep up to date with a specific
branch, use a tag such as
``registry.gitlab.com/rpatterson/prunerr:main``. Releases from ``develop``
publish pre-releases. Releases from ``main`` publish final releases. Releases from
``main`` also publish tags without a branch, for example
``registry.gitlab.com/rpatterson/prunerr``. Releases from ``main`` also
publish tags for the major and minor version, for example
``registry.gitlab.com/rpatterson/prunerr:v0.8``.

Releases publish multi-platform images for the following platforms:

- ``linux/amd64``
- ``linux/arm64``
- ``linux/arm/v7``


****************************************************************************************
Usage
****************************************************************************************

Start by writing your ``~/.config/prunerr.yml`` `configuration file`_.

Once configured, you may run individual sub-commands once, run all operations once as
configured using the ``$ prunerr apply`` sub-command, or run all operations in a polling
loop using the ``$ prunerr daemon`` sub-command. See the `Download Item Life-cycle`_
section for a detailed description of the stages. Use the CLI help to list the other
sub-commands and to get help on the individual sub-commands::

  $ prunerr --help
  $ prunerr apply --help

If using the Docker container image, the container can be run from the command-line as
well::

  $ docker compose run "prunerr" prunerr --help


****************************************************************************************
Configuration File
****************************************************************************************

The default configuration file is ``~/.config/prunerr.yml``, or it can be specified as
an option on the command line, for example::

  $ prunerr --config="/srv/foo-compose-project/prunerr/config/prunerr.yml" ...

See the comments in `the example configuration`_ for details and examples. What items to
apply operations to and optionally how to sort the items to determine the order to apply
actions are determined by rendering `Jinja templates`_.

Users may sometimes want to apply different actions than those in the default
configuration file, for example to review what Prunerr will delete in the ``free-space``
stage or the orphaned files in the ``orphans`` stage without actually deleting them
yet. Copy the configuration file, remove all actions and replace them with appropriate
``log: "..."`` templates, and run Prunerr with that configuration file.


****************************************************************************************
Download Item Life-cycle
****************************************************************************************

Prunerr polls the download clients for all their items. It uses various internal means
to identify which download items are at which point in the Servarr download item
life-cycle or workflow:

The ``$ prunerr apply`` sub-command applies the operations configured for the
life-cycle or workflow stage specified by the ``--stage=*`` option or applies all
operations for the default stages without the ``--stage=*`` option. The ``$ prunerr
daemon`` sub-command does the latter in a loop indefinitely. The default stages are the
following except excluding the `Orphans Stage`_.

Queued Stage
========================================================================================

Items newly added to the download client. These items are identified as queued if `the
download item's 'downloadDir'`_ is an ancestor of `the download client's
'download-dir'`_.

.. note:

   This means Prunerr depends on each Servarr instance using a directory under each
   download client's ``download-dir`` in the corresponding Servarr download client
   settings. This is the case when using the default for the ``Directory`` field under
   the advanced settings, but if that setting is changed as in these examples, the path
   must be a descendant of the download client's ``download-dir``.

For example, if the download client's ``download-dir`` is ``/media/Library/downloads/``
and Servarr sets the download item's ``downloadDir`` to
``/media/Library/downloads/Sonarr/Videos/Series/`` when grabbing it, then Prunerr will
consider it to be queued.

These operations will only be applied once per download item unless the Prunerr
`configuration file`_ has changed. This is accomplished using a ``{{ item.downloadDir
}}/{{ item.hashString }}-prunerr.log`` log file for each download item. To re-apply the
``queued`` operations to all currently queued download items, modify the `configuration
file`_ or just ``$ touch ~/.config/prunerr.yml``. To re-apply the ``queued`` operations
to just one currently queued download item, delete or move aside that item's log file.

For example, these operations can be used to:

- Adjust bandwidth priorities.
- Remove and blacklist archives.
- Remove and blacklist stalled releases.
- etc.

Seeding Stage
========================================================================================

Items that Servarr has acted on and removed from its queue. Usually this happens when
Servarr automatically imported files from the item, but it also happens if the user
intervenes and removes the item from the Servarr queue. Usually, this includes only one
operation, to move items to the parallel ``**/seeding/**`` directory. This path is
assembled by replacing the last element of `the download client's 'download-dir'`_ path
with ``seeding`` in `the download item's 'downloadDir'`_, for example
``/media/Library/seeding/Sonarr/Videos/Series/``:

.. note:

   This means Prunerr depends on `the download client's 'download-dir'`_ not ending in
   ``**/seeding/``.

Free-space Stage
========================================================================================

Available disk space has dropped below the margin configured under ``{{
config["download-clients"]["max-download-*"] }}``. Usually used to define which items
are available for deleting and the order to delete them in. For example:

- Don't delete currently imported items.
- Don't delete private items that haven't met seeding requirements.
- Delete public items first.
- Delete private items in an order to maximize tracker ratio and/or bonuses.
- etc.

This stage is unique in that instead of applying the configured actions to all the
``include:`` items, the ``free-space`` stage applies actions to the ``include:`` items
in the ``sort:`` order **until** the available disk space has risen above the margin
configured under ``{{ config["download-clients"]["max-download-*"] }}``.

For those times when there's nothing Prunerr can delete to free disk space, most users'
download clients should probably also pause downloading when disk space drops
significantly below this margin. Use `the provided Transmission pause download script`_
and optionally `integrate it as a cron job`_ into your `Docker Compose project`_ or see
those as examples.

All Stage
========================================================================================

Always run for all download items under the ``download-dir`` or it's parallel
``**/seeding/`` directory in any stage of the Servarr life-cycle or workflow.

.. warning::

   As such these operations can drastically affect Prunerr's run-time, so performance is
   important. Be careful with the ``include`` template to be both efficient per-item and
   to limit the operation to as few download items as possible.

Usually only used to remove download items that are no longer registered with their
indexer/tracker and to verify corrupt items, both of which can happen to any item at any
time.

.. note::

   This stage excludes download items that have finished downloading and are complete
   but are still in `the download client's 'download-dir'`_ to avoid clashes while
   Servarr instances may be importing download item files.

Orphans Stage
========================================================================================

Prunerr can also identify orphaned files, those not belonging to any download item, in
`the download item's 'downloadDir'`_ and it's parallel parallel ``**/seeding/``
directory. This requires walking all files in those directories and as such takes some
time and shouldn't be run as a part of the ``$ prunerr daemon`` sub-command and as such
is **not** one of the default stages for ``$ prunerr apply``.

The orphans stage is also unique in that, by the nature of orphans, it deals with file
paths instead of download items. Those paths are available in templates as ``{{ item
}}``. As such, some actions cannot be used in operations under ``orphans``. The
supported actions are:

- ``remove: true``
- ``log: "..."``

When there are orphaned files, there can be a lot of orphaned files and dealing with
them individually can be noisy without adding meaning. As such, this stage is also
unique in that while the ``include:`` and ``sort:`` templates are still used to filter
and order the file paths, the actions are applied to **all** orphaned files at once. Any
templates in action configurations can access the orphaned files under the ``{{ paths
}}`` name.

Most users will probably want to use ``$ prunerr apply --stage="orphans"`` as a
periodic maintenance task to report and/or automatically delete orphans, though less
frequently than ``$ prunerr daemon`` would.

.. warning::

   Stop ``$ prunerr daemon`` while running ``$ prunerr apply --stage="orphans"``!

   Prunerr uses the list of files for every download item to identify orphans. If a
   user, Prunerr, or anything else, moves or changes the location of a download item
   while Prunerr is identifying orphans, Prunerr may identify the *new* download item
   data path as an orphan and delete it out from under the download item leading to data
   loss.


****************************************************************************************
Export sub-command
****************************************************************************************

The ``export`` sub-command is roughly the inverse of Servarr import events, hard link
imported files back into download client items and verify. See the CLI ``$ prunerr
export --help`` output for more details.


****************************************************************************************
Notifications
****************************************************************************************

When running the ``$ prunerr daemon`` sub-command, notifications can be sent using
`ntfy`_ when Prunerr encounters errors such as when there's nothing Prunerr can delete
to free disk space.

Unfortunately, ``ntfy`` is somewhat unmaintained so Prunerr includes a more current fork
and branch. Install it's dependencies with the ``ntfy`` extra. for example ``$ pip3
install --user prunerr[ntfy]``. Prunerr reproduces `ntfy's "extra" dependencies`_ for
the specific back-ends, so see those extras and add them for the back-ends you use when
installing Prunerr, for example ``$ pip3 install --user prunerr[ntfy,pid,matrix]``. `The
Docker image`_ includes all extras that are currently working for that image's Python
version.

Then `configure ntfy`_. If using the Docker container, see `the ntfy comment in
./docker-compose.yml`_ for how to bind mount your user's configuration into the
container by using a volume.

****************************************************************************************
Contributing
****************************************************************************************

`GitLab hosts this project`_ and `mirrors it to GitHub`_ but use GitLab for reporting
issues, submitting pull or merge requests and any other development or maintenance
activity. See `the contributing documentation`_ for more details on how to get started
with development.


****************************************************************************************
Motivation
****************************************************************************************

I didn't like the available options I could find at the time for maximizing seeding from
a lovingly managed media library. Deleting by a ratio threshold doesn't make sense to me
because that can delete items when there's plenty of disk space. Also the ratio
threshold is a reverse indicator for items from private indexers vs items from public
indexers. Items from private indexers with high ratios should be kept around as long as
possible to build user total ratio whereas items from public indexers with low ratios
should be kept around as long as possible to preserve access in the community/ecosystem.
Finally, deleting any item still imported in the Servarr only because it hit the ratio
threshold is the biggest waste since it doesn't free any space. So I wrote Prunerr to
prune download items in the correct order.

The use case for Prunerr is not tracker ratio racing. It's goal is to seed as long as
possible and to seed as much of your library as possible. This should have some
secondary benefits to ratio, but that's not the main goal.

Finally, there is a laundry list of other download client management tasks that can be
automated but aren't by anything I could find. So I added them to Prunerr as well.


****************************************************************************************
References
****************************************************************************************

.. target-notes::

.. _`Servarr`: https://wiki.servarr.com
.. _`Transmission BitTorrent client`: https://transmissionbt.com/
.. _`download clients`: https://wiki.servarr.com/radarr/settings#download-clients
.. _`Sonarr`: https://wiki.servarr.com/en/sonarr
.. _`Radarr`: https://wiki.servarr.com/en/radarr
.. _`FlexGet`: https://flexget.com/

.. _pip: https://pip.pypa.io/en/stable/installation/
.. _argcomplete: https://kislyuk.github.io/argcomplete/#installation

.. _`Docker Compose`: https://docs.docker.com/compose/
.. _`the example ./docker-compose.yml file`:
   https://gitlab.com/rpatterson/prunerr/-/blob/main/docker-compose.yml
.. _the Docker image: https://hub.docker.com/r/merpatterson/prunerr

.. _`the example configuration`:
   https://gitlab.com/rpatterson/prunerr/blob/main/src/prunerr/home/.config/prunerr.yml
.. _`Jinja templates`: https://jinja.palletsprojects.com/en/latest/templates/

.. _`the download item's 'downloadDir'`:
   https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md#user-content-41-session-arguments
.. _`the download client's 'download-dir'`:
   https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md#user-content-33-torrent-accessor-torrent-get

.. _`the provided Transmission pause download script`:
   https://gitlab.com/rpatterson/prunerr/blob/main/transmission/usr/local/bin/transmission-pause-download
.. _`integrate it as a cron job`:
   https://gitlab.com/rpatterson/prunerr/blob/main/transmission/etc/crontabs/abc
.. _`Docker Compose project`: `the example ./docker-compose.yml file`_

.. _`ntfy`: https://ntfy.readthedocs.io/en/latest/
.. _`ntfy's "extra" dependencies`: https://ntfy.readthedocs.io/en/latest/#extras
.. _`configure ntfy`: https://ntfy.readthedocs.io/en/latest/#configuring-ntfy
.. _`the ntfy comment in ./docker-compose.yml`:
   https://gitlab.com/rpatterson/prunerr/-/blob/main/docker-compose.yml#L101-103

.. _`GitLab hosts this project`:
   https://gitlab.com/rpatterson/prunerr
.. _`mirrors it to GitHub`:
   https://github.com/rpatterson/prunerr
.. _`the contributing documentation`:
   https://gitlab.com/rpatterson/prunerr/-/blob/main/docs/contributing.rst
