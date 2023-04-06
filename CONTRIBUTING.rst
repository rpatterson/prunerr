########################################################################################
CONTRIBUTING
########################################################################################

Development requires fairly standard development tools, but ``git`` and ``make`` to
bootstrap the local development environment.  Once installed, clone the repository::

  $ git clone "https://gitlab.com/rpatterson/python-project-structure"

Then hand the rest over to the `Makefile`_ to install the VCS hooks the rest of the set
up and build required for local development::

  $ make

If there's not already `an issue/ticket`_ for the changes you'll be making, create one.
Regardless, take note of the issue/ticket number, e.g. ``#123``.  Then create a
branch/fork off of the ``develop`` branch::

  $ git checkout -b feat-123-foo-bar origin/develop

This project uses `towncrier`_ to manage it's release notes, AKA changelog and thus
requires at least one `news fragment`_ before merging back into ``develop``.  The VCS
hooks enforce this when pushing to ``develop`` or ``master``::

  $ towncrier create 123.feature

From there you can begin writing your tests or making other changes and run the tests to
check your work::

  $ make test

You can also inspect test failures and errors in `Python's post-mortem debugger`_::

  $ make test-debug

The ``$ make test`` target also runs the ``$ make format`` target to format code
according to this project's guidelines and rules.

Once work is finished and all the tests are passing, project maintainers can merge your
work and run all checks and tests as above to confirm your work.  Then they can, bump
the version, build release packages, and publish them to PyPI::

  $ make release-bump release

The versions for this project's dependencies and development tools are frozen/fixed for
reproducibility in ``./requirements/**.txt``. The `Makefile`_ will update those versions
as the dependencies change in ``./setup.cfg`` and ``./requirements/build.txt.in``.  Note
that this means other versions may be updated as the published versions for dependencies
are updated on remote indexes/registries.  Maintainers can also update all dependencies
to the latest versions::

  $ make upgrade

See also `the ./TODO.rst file`_ which lists known bugs and desirable features for which
contributions are most welcome.

If changes to development processes, such as build or release processes, are required,
they should be captured in the `Makefile`_.  Similarly, if a development task is
important enough to include in the documentation, then it's important enough to capture
in executable form in the `Makefile`_.  See the philosophy commentary at the bottom of
the `Makefile`_ for guidance on making contributions there.


.. _`Python's post-mortem debugger`:
   https://docs.python.org/3/library/pdb.html#pdb.post_mortem

.. _`towncrier`: https://towncrier.readthedocs.io/en/stable/#philosophy
.. _`news fragment`: https://towncrier.readthedocs.io/en/stable/quickstart.html#creating-news-fragments

.. _`an issue/ticket`: https://gitlab.com/rpatterson/python-project-structure/-/issues

.. _Makefile: ./Makefile
.. _`the ./TODO.rst file`: ./TODO.rst
