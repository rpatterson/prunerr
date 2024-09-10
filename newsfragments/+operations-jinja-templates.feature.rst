:Operations:

   Switch to `Jinja templates <https://jinja.palletsprojects.com/en/latest/templates/>`_
   in the operation configurations for filtering and sorting items. This is a major,
   breaking change and existing users need to re-write everything under the ``indexers``
   and ``operations`` keys and remove the ``priorities`` keys in their
   ``~/.config/prunerr.yml`` configuration files. See these keys in the exmaple
   configuration file and it's comments for details.
