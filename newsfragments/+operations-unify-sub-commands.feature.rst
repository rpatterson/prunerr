:Operations:

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
