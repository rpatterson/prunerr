.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Contributing
########################################################################################

Development requires fairly standard development tools, but ``git`` and ``make`` to
bootstrap the local development environment.  Once installed, clone the repository::

  $ git clone "https://gitlab.com/rpatterson/prunerr"

Then hand the rest over to the `Makefile`_ to install the VCS hooks the rest of the set
up and build required for local development::

  $ make

If there's not already `an issue/ticket`_ for the changes you'll be making, create one.
Regardless, take note of the issue/ticket number, e.g. ``#123``.  Then create a
branch/fork off of the ``develop`` branch::

  $ git switch -c feat-123-foo-bar origin/develop

This project uses `towncrier`_ to manage it's release notes, AKA changelog and thus
requires at least one `news fragment`_ before merging back into ``develop``.  The VCS
hooks enforce this when pushing to ``develop`` or ``main``::

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

The linters make various decisions on style, formatting, and conventions for you so you
don't have to think about them and no one has to debate them.  They're enforced by ``$
make test`` and the VCS hooks.  You may also use the same tools to apply all fixes and
formatting that can be automated to format code according to this project's guidelines
and rules::

  $ make devel-format

This project also uses `Reuse`_ to manage licenses and copyright.  If you add files,
you'll need to put an `SPDX header comment`_ in each added file.  For those file types
recognized by the `reuse-tool`_, you can use ``$ make devel-format`` to add such headers
automatically.  Otherwise you may have to use ``$ reuse addheader`` manually specifying
the appropriate ``--style`` option.  See ``$ reuse addheader --help`` for the available
``${COMMENT_STYLE}`` values.  You can use ``--style "python"`` for unrecognized file
types that support the common ``#`` comment style::

  $ tox exec -e build -- reuse addheader --style "${COMMENT_STYLE:?}" \
  --copyright "Ross Patterson <me@rpatterson.net>" --license "MIT" "${PATH:?}"

Contributions should be pushed to feature branches or forks off of the upstream
``develop`` branch.  Once work is finished and all the tests are passing locally, open a
merge/pull request (MR) against the upstream ``develop`` branch.  Address any issues
revealed by any failed CI/CD jobs for your MR.  Once all CI/CD checks are green, project
maintainers can merge your work where CI/CD will publish a pre-release for your changes
including container images and PyPI packages.  Contributors should then test the
pre-release, preferably with as many users and use cases as possible.  Once everything
looks good and the project maintainers think it's time to make a final release with all
the outstanding work on ``develop``, they can merge ``develop`` into ``main`` and CI/CD
will then publish a final release.

The versions for this project's dependencies and development tools are frozen/fixed for
reproducibility in ``./requirements/**.txt``. The `Makefile`_ will update those versions
as the dependencies change in ``./setup.cfg`` and ``./requirements/build.txt.in``.  Note
that this means other versions may be updated as the published versions for dependencies
are updated on remote indexes/registries.  Maintainers can also update all dependencies
to the latest versions::

  $ make devel-upgrade

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
.. _`news fragment`:
   https://towncrier.readthedocs.io/en/stable/quickstart.html#creating-news-fragments
.. _`Reuse`: https://reuse.software/tutorial/#step-2
.. _`SPDX header comment`: https://spdx.dev/specifications/#current-version
.. _`reuse-tool`: https://github.com/fsfe/reuse-tool#usage

.. _`an issue/ticket`: https://gitlab.com/rpatterson/prunerr/-/issues

.. _Makefile: ./Makefile
.. _`the ./TODO.rst file`: ./TODO.rst
