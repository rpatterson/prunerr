prunerr 3.0.0b1 (2024-09-30)
============================

Features
--------

- :Export: Add a new ``export`` sub-command that is roughly the inverse of Servarr import
           events, hard link imported files back into download client items and verify.
- :Operations:

     Switch to `Jinja templates <https://jinja.palletsprojects.com/en/latest/templates/>`_
     in the operation configurations for filtering and sorting items.
- :Operations:

     Unify the sub-commands that were run as a part of ``$ prunerr exec`` as different
     download item life-cycle stage operations. This is a major,
     breaking change and existing users need to:

     #. Re-read the `README
        <https://gitlab.com/rpatterson/prunerr/-/blob/main/README.rst>`_ to understand how
        Prunerr works after these changes.

     #. Re-read the `the example configuration
        <https://gitlab.com/rpatterson/prunerr/blob/main/src/prunerr/home/.config/prunerr.yml>`_
        and the comments there to understand how to configure Prunerr after these changes.

     #. Re-write the ``~/.config/prunerr.yml`` configuration file. Only the ``servarrs:``,
        ``download-clients:``, and ``daemon:`` keys remain the same. The changes to the
        rest are significant and structural and as such there's no simple directions to
        update existing configurations.
- :Operations: Make the ``type: "files"`` operation more flexible to support filtering on
               file attributes. Needed to reproduce the ``size_imported`` use case but
               only on wanted/selected files.
- :Re-add: Add a new ``re-add`` sub-command to remove and re-add all seeding download
           items with nothing downloaded. This is useful to avoid re-verifying seeding
           items when Transmission loses track of the items progress such as when it's
           ``/config/resume/*.resume`` files are lost or recreated.


Bugfixes
--------

- :free-space: Also consider files in the Transmission ``incomplete-dir`` when identifying
               item files as orphans to delete.
- :free-space: Also consider unselected/unwanted download item files as orphans to delete.
- :free-space: Avoid deleting incomplete files from under newly added download items while
               identifying orphans.
- :free-space: Consider sparse files and hard links when calculating real storage usage.
- :free-space: Prevent download clients under heavy load from blocking the freeing of disk
               space.
- :free-space: Send a notification when nothing can be deleted to keep sufficient free
               space.
- :free-space: Switch from start date to added date when guessing torrent time since done
               when the done date is missing.
- :free-space: Tolerate but log when a previous ``$ prunerr free-space`` run deleted the
               files but the download client, under heavy load, fails to remove the item.
- :free-space: Too broad socket connection error exception catch.
- :move: Avoid interrupting Servarr import, don't move download items until some time has
         passed since the most recent import.
- :operations: Avoid division by zero when no files are selected and using the ``portion``
               option for the item files operation results.
- :review: TODO



     Run configured operations on download items upgraded by a newly imported download
         item along with the related Servarr history to, for example, conditionally send
         notifications when an upgrade may need further attention.
- Upgrade all requirements to the most recent versions as of
  Sun Aug 18 12:40:22 AM UTC 2024.


Deprecations and Removals
-------------------------

- :free-space: Remove support for pausing/resuming download out of Prunerr and into the
               download client container via a cron job.



