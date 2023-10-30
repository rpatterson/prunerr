prunerr 2.0.0b2 (2023-10-30)
============================

Bugfixes
--------

- Fix handling of empty top-level keys in the configuration file::

    DEBUG:prunerr.runner:Sub-command `exec` completed in 89.50181317329407s
    Traceback (most recent call last):
      File "/usr/local/bin/prunerr", line 8, in <module>
        sys.exit(main())
                 ^^^^^^
      File "/usr/local/lib/python3.11/site-packages/prunerr/__init__.py", line 241, in main
        _main(args=args)
      File "/usr/local/lib/python3.11/site-packages/prunerr/__init__.py", line 288, in _main
        if (result := parsed_args.command(runner, **command_kwargs)) is not None:
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File "/usr/local/lib/python3.11/site-packages/prunerr/__init__.py", line 181, in daemon
        runner.daemon(*args, **kwargs)
      File "/usr/local/lib/python3.11/site-packages/prunerr/runner.py", line 337, in daemon
        poll = self.config.get("daemon", {}).get("poll", 60)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    AttributeError: 'NoneType' object has no attribute 'get'
- Get default values from `the example configuration file
  <https://gitlab.com/rpatterson/prunerr/blob/main/src/prunerr/home/.config/prunerr.yml>`_.



