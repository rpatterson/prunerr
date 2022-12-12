************
CONTRIBUTING
************

Development requires fairly standard development tools, but ``git`` and ``make`` to
bootstrap the local development environment.  Once installed, clone the repository::

  $ git clone "https://gitlab.com/rpatterson/prunerr"

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
check your work.  For reproducibility and to expose clean build issues, the tests can be
run inside the development container.  This is the command run by the VCS hooks and the
``$ make test`` target as well::

  $ make test-docker

During the inner loop of development iterations, it may be more efficient to run the
tests locally directly on your development host::

  $ make test-local

You can also inspect test failures and errors in `Python's post-mortem debugger`_.  This
also runs locally directly on your development host::

  $ make test-debug

The ``$ make test`` target also runs the ``$ make format`` target to format code
according to this project's guidelines and rules.

Once work is finished and all the tests are passing locally, open a PR and push your
changes there.  Address any issues revealed by any failed CI/CD jobs for your PR
branch/fork.  Once all CI/CD checks are green, project maintainers can merge your work
into the ``develop`` branch where CI/CD will publish a pre-release for your changes.
When the project maintainers think it's time to make a final release with all the
outstanding work on ``develop``, they can merge ``develop`` into ``master`` and CI/CD
will then publish a final release including container images and PyPI packages.  Project
maintainers may test the release process locally using the `Makefile`_::

  $ make build-bump test-docker release

The versions for this project's dependencies and development tools are frozen/fixed for
reproducibility in ``./requirements*.txt``. The `Makefile`_ will update those versions
as the dependencies change in ``./setup.cfg`` and ``./requirements-build.txt.in``.  Note
that this means other versions may be updated as the published versions for dependencies
are updated on remote indexes/registries.  Maintainers can also update all dependencies
to the latest versions::

  $ make upgrade

See also `the ./TODO.rst file`_ which lists known bugs and desirable features for which
contributions are most welcome.


.. _`Python's post-mortem debugger`:
   https://docs.python.org/3/library/pdb.html#pdb.post_mortem

.. _`towncrier`: https://towncrier.readthedocs.io/en/stable/#philosophy
.. _`news fragment`: https://towncrier.readthedocs.io/en/stable/quickstart.html#creating-news-fragments

.. _`an issue/ticket`: https://gitlab.com/rpatterson/prunerr/-/issues

.. _Makefile: ./Makefile
.. _`the ./TODO.rst file`: ./TODO.rst
