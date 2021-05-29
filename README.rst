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


.. _`Servarr`: https://wiki.servarr.com
