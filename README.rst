#######
Prunerr
#######
Remove Servarr download client items to preserve disk space according to rules.
*******************************************************************************

The ``$ prunerr`` command is intended to server as a companion service to the `Servarr`_
suite of applications and services.  It periodically polls the `download clients`_ of
`Sonarr`_, `Radarr`_, etc..  For each client it checks disk space compared to download
rate and selectively removes items and deletes item data to maintain a healthy margin of
disk space.  Download items are deleted in an order determined by a set of rules and
criteria that can be defined on a per-indexer basis.  This is mostly useful for
`BitTorrent`_ download clients in order to maximize ratio on a per-indexer/per-tracker
basis.

The Servarr state of download items (grabbed, downloading, imported, and/or deleted)
must be reflected in the download client in order to do the above.  Servarr instances
use the ``$ ./bin/prunerr handle ...`` sub-command as a `Servarr Custom Script`_ under
the ``Connect`` Servarr settings to accomplish this.

Prunerr uses and requires a configuration file which default to
``~/.config/prunerr.yml``.  See the well-commented sample configuration:
`<./home/.config/prunerr.yml>`_.

TODO: Download clients on different filesystems, copying


*******************
Order of Operations
*******************

Note that polling is required because there is no reliable event we can respond to that
reliably determines disk space margin *as* the downlod clients are downloading.

#. Identify and report orphan files and directories:

   Walk all the top-level directories used by each download client and identify which
   paths don't correspond to a download client item.

#. Identify and report un-managed download items:

   Compare all download client items against those added by each `Servarr`_ application
   to identify those that weren't added by a `Servarr`_ application and are therefor
   un-managed or managed by something else.  Note that these items aren't considered for
   deletion.

#. Order download items according to per-indexer rules:

   Apply the per-indexer/per-tracker rules to each item and use the results to define the
   order in which to delete items as needed for disk space.

#. Calculate required disk margin based on download speed:

   Get the average download speed for each download client and multiply it by an amount
   of time it should be able to continue downloading for to determine the disk space
   margin we should preserve.

   TODO: Issues with instantaneous download speed?

#. Remove/delete download client items until margin is reached:

   Per the order from #3, remove one download client item at a time and delete it's
   data, wait until the data can be confirmed as deleted, check disk space again and
   repeat as needed until the margin is reached.

#. Stop downloading if the disk space margin can't be reached

   If the margin can't be reached, report an error and stop the download client from
   downloading any further data.  This is useful to avoid a number of issues that can
   happen if disk space is fully exhausted, including corrupted download client state
   and/or data.

   TODO: Notifications?

TODO: Mark stalled torrents as failed in Servarr

*********************
Servarr Custom Script
*********************

Prunerr reflects the Servarr state of download items in the state of items in the
download client, similar to the design principles of Servarr applications, as opposed to
say a DB or some other external persistent storage because.  This allows the user to
inspect Prunerr/Servarr state in the native UI for the download client, supports manual
user intervention, and avoids an additional dependency.

Specifically, Prunerr moves the location of download client items as items proceed
through the Servarr workflow: ``./downloads/**`` -> ``./imported/**`` ->
``./deleted/**``.  In order to reflect which individual files have been imported and
where, Prunerr also creates ``./*-ServarrName-import.ln`` symbolic links next to the
download client item as individual files are imported by Servarr instances.  This way,
broken symlinks are an indicator of upgraded files.

Prunerr needs to know which Servarr instance is invoking ``$ prunerr handle`` in order
to use the correct Prunerr configuration.  Unfortunately, Servarr doesn't support
passing any arguments to Custom Scripts.  As such, using Prunerr as a Custom Script
requires a wrapper script that in turn calls ``$ prunerr handle ${servarr_name}``.  This
wrapper script is what should be used in the ``Path`` field of the Servarr Custom Script
settings. See `<./home/.local/bin/prunerr-sonarr-handle>`_ and
`<./home/.local/bin/prunerr-radarr-handle>`_ for examples.

If the Servarr instance is running in a container, Servarr Custom Scripts must be
executable inside the same container as the Servarr instance.  Since Prunerr does not
support `Python 2.x`_, this means the `linuxserver.io`_ containers are incompatible with
Prunerr.  The `hotio`_ containers are similarly well maintained and do include `Python
3.x`_ so those images *are* compatible with Prunerr.  This also means that Prunerr must
be installed into the container.  See `<./docker-compose.yml>`_ for examples of how to
stitch all this together in a deployment in containers.

Prunerr also provides a ``$ ./bin/prunerr sync`` sub-command to introspect the item
history from Servarr instances and apply any appropriate state that can be determined
from the Servarr history to the download client items.  This sub-command can be used to
get any existing download client items in sync as if they had been processed by the
``$ prunerr handle ...``.

****************
Other Operations
****************

The ``$ prunerr`` command can also be used to perform other operations outside of the
main polling loop above, such as CLI management commands and responding to events in the
system such as events from download clients and/or `Servarr`_ applications.

- Set per-indexer/per-tracker priority for items in download clients

.. _`Python 3.x`: https://docs.python.org/3/
.. _`Python 2.x`: https://www.python.org/doc/sunset-python-2/

.. _`BitTorrent`: https://en.wikipedia.org/wiki/BitTorrent

.. _`Servarr`: https://wiki.servarr.com
.. _`Radarr`: https://wiki.servarr.com/en/radarr
.. _`Sonarr`: https://wiki.servarr.com/en/sonarr
.. _`download clients`: https://wiki.servarr.com/radarr/settings#download-clients

.. _`linuxserver.io`: https://docs.linuxserver.io/images/docker-radarr
.. _`hotio`: https://hotio.dev/containers/radarr/
