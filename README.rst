#######
Prunerr
#######
Remove Servarr download client items to preserve disk space according to rules.
*******************************************************************************

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
       .. figure:: https://gitlab.com/rpatterson/prunerr/badges/master/pipeline.svg
          :alt: GitLab CI/CD pipeline status
          :target: https://gitlab.com/rpatterson/prunerr/-/commits/master
       .. figure:: https://gitlab.com/rpatterson/prunerr/badges/master/coverage.svg
          :alt: GitLab coverage report
	  :target: https://gitlab.com/rpatterson/prunerr/-/commits/master
       .. figure:: https://img.shields.io/gitlab/stars/rpatterson/prunerr?gitlab_url=https%3A%2F%2Fgitlab.com&logo=gitlab
	  :alt: GitLab repo stars
	  :target: https://gitlab.com/rpatterson/prunerr

     - .. figure:: https://img.shields.io/github/v/release/rpatterson/prunerr?logo=github
	  :alt: GitHub release (latest SemVer)
	  :target: https://github.com/rpatterson/prunerr/releases
       .. figure:: https://github.com/rpatterson/prunerr/actions/workflows/ci-cd.yml/badge.svg
          :alt: GitHub Actions status
          :target: https://github.com/rpatterson/prunerr/
       .. figure:: https://codecov.io/github/rpatterson/prunerr/branch/master/graph/badge.svg?token=GNKVQ8VYOU 
          :alt: Codecov test coverage
	  :target: https://codecov.io/github/rpatterson/prunerr
       .. figure:: https://img.shields.io/github/stars/rpatterson/prunerr?logo=github
	  :alt: GitHub repo stars
	  :target: https://github.com/rpatterson/prunerr/

     - .. figure:: https://img.shields.io/docker/v/merpatterson/prunerr?sort=semver&logo=docker
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

Or use `the Docker image`_.  See `the example ./docker-compose.yml file`_ for usage details.


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


.. _`Transmission BitTorrent client`: https://transmissionbt.com/

.. _`Servarr`: https://wiki.servarr.com
.. _`Radarr`: https://wiki.servarr.com/en/radarr
.. _`Sonarr`: https://wiki.servarr.com/en/sonarr
.. _`download clients`: https://wiki.servarr.com/radarr/settings#download-clients

.. _the example ./docker-compose.yml file: https://github.com/rpatterson/prunerr/blob/master/docker-compose.yml
.. _the Docker image: https://hub.docker.com/r/merpatterson/prunerr
