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
       .. figure:: https://img.shields.io/pypi/dm/prunerr.svg?color=blue&label=Downloads&logo=pypi&logoColor=gold
          :alt: PyPI downloads per month
          :target: https://pypi.org/project/prunerr/
       .. figure:: https://img.shields.io/pypi/pyversions/prunerr.svg?logo=python&label=Python&logoColor=gold
          :alt: PyPI Python versions
          :target: https://pypi.org/project/prunerr/
       .. figure:: https://img.shields.io/badge/code%20style-black-000000.svg
          :alt: Python code style
          :target: https://github.com/psf/black

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
	  :alt: GitLab repo stars
	  :target: https://gitlab.com/rpatterson/prunerr

     - .. figure:: https://img.shields.io/github/v/release/rpatterson/prunerr?logo=github
	  :alt: GitHub release (latest SemVer)
	  :target: https://github.com/rpatterson/prunerr/releases
       .. figure:: https://github.com/rpatterson/prunerr/actions/workflows/build-test.yml/badge.svg
          :alt: GitHub Actions status
          :target: https://github.com/rpatterson/prunerr/actions/workflows/build-test.yml
       .. figure:: https://codecov.io/github/rpatterson/prunerr/branch/main/graph/badge.svg?token=GNKVQ8VYOU
          :alt: Codecov test coverage
	  :target: https://codecov.io/github/rpatterson/prunerr
       .. figure:: https://img.shields.io/github/stars/rpatterson/prunerr?logo=github
	  :alt: GitHub repo stars
	  :target: https://github.com/rpatterson/prunerr/

     - .. figure:: https://img.shields.io/docker/v/merpatterson/prunerr/main?sort=semver&logo=docker
          :alt: Docker Hub image version (latest semver)
          :target: https://hub.docker.com/r/merpatterson/prunerr
       .. figure:: https://img.shields.io/docker/pulls/merpatterson/prunerr?logo=docker
          :alt: Docker Hub image pulls count
          :target: https://hub.docker.com/r/merpatterson/prunerr
       .. figure:: https://img.shields.io/docker/stars/merpatterson/prunerr?logo=docker
	  :alt: Docker Hub stars
          :target: https://hub.docker.com/r/merpatterson/prunerr
       .. figure:: https://img.shields.io/docker/image-size/merpatterson/prunerr?logo=docker
	  :alt: Docker Hub image size (latest semver)
          :target: https://hub.docker.com/r/merpatterson/prunerr

TL;DR: Perma-seeding of whole Servarr libraries optimized for per-tracker ratio.

- Delete torrents/items only as disk space gets low.
- Don't delete currently imported items.  IOW, only delete upgraded items.
- Don't delete private items that haven't met seeding requirements.
- Delete public items first
- Delete private items in an order to maximize tracker ratio and/or bonuses.
- And more...

*******
Summary
*******

Seed Servarr download client torrents/items as long as possible only deleting them as
necessary as disk space gets low, hence the name based on "to prune".  Which download
items are considered eligible for deletion is configured by the user.  The common case
is that download items that are currently imported are not considered for deletion.
Neither are items from private trackers/indexers that have been upgraded or otherwise
deleted from the library but haven't met the indexers seeding requirements.  The order
in which download items are deleted is determined according to rules configured by the
user.  The common case is to delete items from public indexers first and among those to
delete the items with the highest ratio first to preserve the health of the community by
seeding less popular items longer.  Next delete items from private indexers by
configured indexer priority and within the items for a given indexer to delete items in
an order to maximize ratio and/or seeding rewards.

Other configured operations may be applied as well.  For example:

- Verify and resume corrupt items
- Increase bandwidth priority for items from private indexers
- Decrease bandwidth priority for items from public indexers
- Remove and blacklist download items containing archives (``*.rar``, ``*.zip``,
  ``*.tar.gz``, etc.) which can't be perma-seeded
- Remove and blacklist stalled download items
- etc.

The ``$ prunerr`` command is intended to serve as a companion to the `Servarr`_ suite of
applications and services and the `Transmission BitTorrent client`_.  It periodically
polls the `download clients`_ of `Sonarr`_, `Radarr`_, etc. and applies the configured
operations to the download items in each of those download clients.  It can also be run
independently of any Servarr instances to optimize seeding for download items added by
other means, e.g. `FlexGet`_.

See the `Usage`_ section below for full details.


****************************************************************************************
Installation
****************************************************************************************

Install using any tool for installing standard Python 3 distributions such as `pip`_::

  $ sudo pip3 install prunerr

Optional shell tab completion is available via `argcomplete`_.

Or use `the Docker image`_.  See `the example ./docker-compose.yml file`_ for usage
details.


****************************************************************************************
Usage
****************************************************************************************

Start by writing your ``~/.config/prunerr.yml`` configuration file.  See the comments in
`the example configuration`_ for details.

Once configured, you may run individual sub-commands once, run all operations once as
configured using the ``$ prunerr exec`` sub-command, or run all operations in a polling
loop using the ``$ prunerr daemon`` sub-command.  See the `Order of Operations`_ section
for a detailed description of the operations.  Use the CLI help to list the other
sub-commands and to get help on the individual sub-commands::

  $ prunerr --help
  $ prunerr exec --help

Set the ``DEBUG`` environment variable to ``true`` to get verbose details and help
understand what Prunerr is doing::

  $ DEBUG=true prunerr exec


*******************
Order of Operations
*******************

Note that polling is required because there is no event we can subscribe to that
reliably determines disk space margin *as* the download clients are downloading.  Every
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
   that directory.  This has the added benefit of reflecting which items have been acted
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
      operations with ``filter: true``.  For example, don't delete currently imported
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
   downloading by setting the download bandwidth limit to ``0``.  IOW, keep seeding, but
   no more downloading until a future ``$ prunerr free-space`` run is able to free
   sufficient space.

   For the orphans group, delete smaller items first to minimize the amount of
   re-downloading needed should the user notice and correct any issues resulting in the
   orphans.

   For the other groups delete items in the order determined by the configured
   ``indexers/priorities`` indexer order then by the configured operations for that
   item's indexer.


****************************************************************************************
CONTRIBUTING
****************************************************************************************

NOTE: `This project is hosted on GitLab`_.  There's `a mirror on GitHub`_ but please use
GitLab for reporting issues, submitting PRs/MRs and any other development or maintenance
activity.

See `the ./CONTRIBUTING.rst file`_ for more details on how to get started with
development.


****************************************************************************************
Motivation
****************************************************************************************

I didn't like the available options I could find at the time for maximizing seeding from
a lovingly managed media library.  Deleting by a ratio threshold doesn't make sense to
me because that can delete items when there's plenty of disk space.  Also the ratio
threshold is a reverse indicator for items from private indexers vs items from public
indexers.  Items from private indexers with high ratios should be kept around as long as
possible to build user total ratio whereas items from public indexers with low ratios
should be kept around as long as possibility to preserve access in the
community/ecosystem.  Finally, deleting any item still imported in the Servarr just
because it hit the ratio threshold is the biggest waste since it doesn't free any space.
So I wrote Prunerr to prune download items in the correct order.

Finally, there is a laundry list of other download client management tasks that can be
automated but aren't by anything I could find.  So I added them to Prunerr as well.


.. _`Transmission BitTorrent client`: https://transmissionbt.com/

.. _`Servarr`: https://wiki.servarr.com
.. _`Radarr`: https://wiki.servarr.com/en/radarr
.. _`Sonarr`: https://wiki.servarr.com/en/sonarr
.. _`download clients`: https://wiki.servarr.com/radarr/settings#download-clients
.. _`FlexGet`: https://flexget.com/

.. _pip: https://pip.pypa.io/en/stable/installation/
.. _argcomplete: https://kislyuk.github.io/argcomplete/#installation

.. _the Docker image: https://hub.docker.com/r/merpatterson/prunerr
.. _`the example ./docker-compose.yml file`: https://gitlab.com/rpatterson/prunerr/blob/master/docker-compose.yml

.. _`the example configuration`:
   https://gitlab.com/rpatterson/prunerr/blob/master/src/prunerr/home/.config/prunerr.yml

.. _`This project is hosted on GitLab`:
   https://gitlab.com/rpatterson/prunerr
.. _`a mirror on GitHub`:
   https://github.com/rpatterson/prunerr

.. _`the ./CONTRIBUTING.rst file`:
   https://gitlab.com/rpatterson/prunerr/blob/master/CONTRIBUTING.rst
