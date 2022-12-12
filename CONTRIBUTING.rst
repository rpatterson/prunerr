************
CONTRIBUTING
************

Development requires fairly standard development tools, but ``git`` and ``make`` to
bootstrap the local development environment.  Once installed, clone the repository::

  $ git clone "https://gitlab.com/rpatterson/python-project-structure"

Then hand the rest over to the `Makefile`_ to install the VCS hooks the rest of the set
up and build required for local development::

  $ make

From there you can begin writing your tests or making other changes and run the tests to
check your work::

  $ make test

You can also inspect test failures and errors in `Python's post-mortem debugger`_::

  $ make test-debug

The ``$ make test`` target also runs the ``$ make format`` target to format code
according to this project's guidelines and rules.

Once work is finished and all the tests are passing, project maintainers can merge your
work, bump the version, run all checks and tests to confirm your work, build release
packages, and publish them to PyPI::

  $ make build-bump test release

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

.. _Makefile: ./Makefile
.. _`the ./TODO.rst file`: ./TODO.rst
