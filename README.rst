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
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L29-42>`_.
- Don't delete `currently imported items
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L187-196>`_.
  IOW, only delete upgraded items.
- Don't delete `private items that haven't met seeding requirements
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L159-186>`_.
- Delete `public items first
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L151-153>`_.
- Delete private items in `an order to maximize tracker ratio and/or bonuses
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L197-218>`_.
- Delete `stalled items
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L60-86>`_
  , and `items containing archives such as *.rar
  releases
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L87-106>`_
  and `blacklist them
  <https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml#L106>`_,
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

Start by writing your ``~/.config/prunerr.yml`` configuration file. See the comments in
`the example configuration`_ for details.

Once configured, you may run individual sub-commands once, run all operations once as
configured using the ``$ prunerr exec`` sub-command, or run all operations in a polling
loop using the ``$ prunerr daemon`` sub-command. See the `Order of Operations`_ section
for a detailed description of the operations. Use the CLI help to list the other
sub-commands and to get help on the individual sub-commands::

  $ prunerr --help
  $ prunerr exec --help

If using the Docker container image, the container can be run from the command-line as
well::

  $ docker compose run "prunerr" prunerr --help


****************************************************************************************
Order of Operations
****************************************************************************************

Note that polling is required because there is no event we can subscribe to that
reliably determines disk space margin *as* the download clients are downloading. Every
run of the ``$ prunerr exec`` sub-command or every loop of the ``$ prunerr daemon``
sub-command performs the following operations.

#. Verify and resume corrupt items, same as: ``$ prunerr verify``.

#. Review download items, same as: ``$ prunerr review``:

   Apply per-indexer review operations as configured under ``indexers/reviews`` in the
   configuration file to all download items.

#. Move download items that have been acted on by Servarr to the ``*/seeding/*``
   directory, same as: ``$ prunerr move``.

   As Servarr acts on completed download items, be that importing files from them,
   ignoring them, deleting them from the queue, etc., Prunerr moves those items from the
   Servarr download client's ``Directory`` to a parallel ``*/seeding/*`` directory.
   Then when deleting download items to free space, Prunerr only considers items under
   that directory. This has the added benefit of reflecting which items have been acted
   on by Servarr in the download client.

#. Delete download items if disk space is low, same as: ``$ prunerr free-space``.

   Consider items for deletion in different groups in this order:

   #. Download items no longer registered with tracker.

      IOW, items that can no longer be seeded at all first.

   #. Orphan files and directories not belonging to any download item

      Walk all the top-level directories used by each download client and identify which
      paths don't correspond to a download client item.

   #. Imported/seeding download items

      IOW, download items that have been acted upon by Servarr and moved to the
      ``*/seeding/*`` directory by the ``$ prunerr move`` sub-command/operation
      excluding those items filtered out according to the ``indexers/priorities``
      operations with ``filter: true``. For example, don't delete currently imported
      items (by hard link count) or items that haven't met private indexer seeding
      requirements.

   For each of these groups in order, loop through each item in the group and:

   #. Check disk space against the margin configured by
      ``download-clients/max-download-bandwidth`` and
      ``download-clients/min-download-time-margin``

   #. If there's sufficient disk space, remove any bandwidth limits set previously and
      continue to the next operation if any.

   #. Otherwise, delete the item.

   If there's still not enough disk space after going through all the groups, then stop
   downloading by setting the download bandwidth limit to ``0``. IOW, keep seeding, but
   no more downloading until a future ``$ prunerr free-space`` run is able to free
   sufficient space.

   For the orphans group, delete smaller items first to minimize the amount of
   re-downloading needed should the user notice and correct any issues resulting in the
   orphans.

   For the other groups delete items in the order determined by the configured
   ``indexers/priorities`` indexer order then by the configured operations for that
   item's indexer.

The Docker container image can run the command-line script as well::

  $ docker compose run "prunerr" prunerr --help
  usage: prunerr [-h]

  prunerr foundation or template, top-level package.

  optional arguments:
    -h, --help  show this help message and exit


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

.. _`GitLab hosts this project`:
   https://gitlab.com/rpatterson/prunerr
.. _`mirrors it to GitHub`:
   https://github.com/rpatterson/prunerr
.. _`the contributing documentation`:
   https://gitlab.com/rpatterson/prunerr/-/blob/main/docs/contributing.rst
