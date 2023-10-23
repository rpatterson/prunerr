.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Contributing
########################################################################################

Development requires standard tools, including ``git``, ``make``, and `Docker`_. Clone
the repository::

  $ git clone "https://gitlab.com/rpatterson/project-structure"

Set up for local development and install the Version Control System (VCS) integration::

  $ make

Create an `issue or ticket`_ for the changes if one doesn't exist. Take note of its
number, for example ``#123``. Create a branch or fork off the ``develop`` branch::

  $ git switch -c feat-123-foo-bar --track origin/develop

`Towncrier`_ manages release notes. Changes require at least one `news fragment`_. The
VCS integration enforces this when pushing::

  $ towncrier create 123.feature

Write tests that describe your changes. Make changes and run tests to confirm your
work::

  $ make test

You can use a debugger to inspect tests::

  $ make test-debug

The linters make decisions on style and formatting. This encourages consistency and
minimizes debate. The ``$ make test`` target and the VCS integration enforce those
policies. You can use the same tools to apply automated fixes and formatting::

  $ make devel-format

`Reuse`_ manages licenses and copyright. Put a `Software Package Data Exchange (SPDX)
header`_ in added files. Use ``$ make devel-format`` to add them for types recognized by
the `reuse-tool`_. Otherwise use ``$ reuse annotate`` manually. Specify the appropriate
``--style`` option. See ``$ reuse annotate --help`` for supported styles. Use ``--style
"python"`` for other file types that support ``#`` comments::

  $ tox exec -e build -- reuse annotate --style "${COMMENT_STYLE:?}" \
  --copyright "Ross Patterson <me@rpatterson.net>" --license "MIT" "${PATH:?}"

Maintainers can merge your work back into ``develop`` and run all checks and tests to
confirm the merge. If successful, they bump the version, build pre-release packages, and
publish to package registries and indexes::

  $ make release

Test the pre-release with all users and use cases possible. If testing doesn't find any
issues, maintainers merge ``develop`` into ``main`` and publish final releases::

  $ make release

The ``./requirements/**.txt`` files lock versions of dependencies and development tools
for reproducibility. The `Makefile`_ updates those when dependencies change in
``./setup.cfg`` and ``./requirements/build.txt.in``. Other versions might get updated
when maintainers publish newer versions. Maintainers can also update all dependencies to
current versions::

  $ make devel-upgrade

See `the TODO file`_ for known bugs and desirable features.

Capture changes to development processes, such as build or release processes, in the
`Makefile`_. Tasks important enough to include in the docs are important enough to
capture in a machine runnable form in the `Makefile`_. See the commentary at the bottom
of the `Makefile`_ for guidance.

.. _`Docker`: https://docs.docker.com/engine/install/#supported-platforms
.. _`issue or ticket`: https://gitlab.com/rpatterson/project-structure/-/issues
.. _`Towncrier`: https://towncrier.readthedocs.io/en/stable/#philosophy
.. _`news fragment`:
   https://towncrier.readthedocs.io/en/stable/tutorial.html#creating-news-fragments
.. _`Reuse`: https://reuse.software/tutorial/#step-2
.. _`Software Package Data Exchange (SPDX) header`: https://spdx.dev/use/specifications/
.. _`reuse-tool`: https://reuse.software/dev/#tool
.. _Makefile: https://gitlab.com/rpatterson/project-structure/-/blob/main/Makefile
.. _`the TODO file`:
   https://gitlab.com/rpatterson/project-structure/-/blob/main/docs/todo.rst
