.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Most wanted contributions
########################################################################################

Known bugs and wanted features.

TEMPLATE: clear items and add items for your project.


****************************************************************************************
Required
****************************************************************************************

#. ``base``: Investigate `Sphinx TODO extension
   <https://www.sphinx-doc.org/en/master/usage/extensions/todo.html>`_.

#. ``base``: Restore `general and module Sphinx indexes
   <https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#special-names>`_
   in the branches for appropriate project types.

#. ``base``: Publish Sphinx docs to `all available documentation hosts
   <https://www.sphinx-doc.org/en/master/faq.html#using-sphinx-with>`_.

#. Investigate recommended third-party Sphinx extensions:
   - https://github.com/yoloseem/awesome-sphinxdoc
   - https://sphinx-extensions.readthedocs.io/en/latest/

#. ``base``: Add an Open Collective badge.


****************************************************************************************
High priority
****************************************************************************************

#. Any documentation improvements:

   Docs benefit most from fresh eyes. If you find anything confusing, ask for help. When
   you understand better, contribute changes to the docs to help others.


****************************************************************************************
Nice to have
****************************************************************************************

#. ``base``: Better final release notes when nothing changed after the last pre-release.

#. ``base``: `Homebrew formula and badge <https://formulae.brew.sh/formula/commitizen>`_

#. ``base``: Try out `other Sphinx themes
   <https://www.sphinx-doc.org/en/master/tutorial/more-sphinx-customization.html#using-a-third-party-html-theme>`_

#. ``base``: Switch to `the badge formatting
   <https://rstcheck-core.readthedocs.io/en/latest/#>`_ from ``rstcheck``

#. ``base``: Upgrade Vale when they publish a release that fixes `the 'script run:
   Compile Error: unresolved reference' errors
   <https://github.com/errata-ai/vale/issues/697#issue-1932675573>`_.

#. ``base``: Try some of `the linters and formatters
   <https://unibeautify.com/docs/beautifier-stylelint>`_ supported by ``UniBeautify``:
   - ``Stylelint`` `CSS linter <https://stylelint.io/>`_
   - `js-beautify <https://www.npmjs.com/package/js-beautify>`_

#. `Docker image build-time labels
   <https://specs.opencontainers.org/image-spec/annotations/?v=v1.0.1>`_::

     org.opencontainers.image.revision
     org.opencontainers.image.ref.name
     org.opencontainers.image.base.digest

#. Container image variants, for example ``*:slim`` or ``*:alpine``:

   The might save less disk space than by using the most widely used base image, given
   that `different images share common image layers
   <https://hub.docker.com/_/buildpack-deps/>`_. This might also have security benefits
   but it also increases risk of incompatibility bugs, whether in the libraries or in
   distribution differences. As such, this probably isn't worth the effort until users
   report convincing use cases.

#. CI/CD for other image platforms:

   This would cause one issue with CI resources. The pipelines already exhaust too much
   of the GitLab free CI/CD minutes for each run. Running the tests in ARM images would
   either consume even more free CI/CD minutes to run on cloud ARM runners. Or would
   take forever by using emulation in the dedicated project runners.

   Docker also lacks important support, creating another issue. Docker provides both the
   capability to build images for non-native platforms *and* run images for non-native
   platforms, both under QEMU emulation, albeit with a significant performance
   penalty. It seems support exists to build a non-native image, run the tests in it,
   and then publish it after passing. But Docker doesn't support local access to built
   multi-platform images, it only supports pushing them to a registry or exporting them
   to some form of filesystem archive. This means following runs of the image tag might
   use a different image than the one built locally. Someone else could have pushed
   another build to the registry between the push and following pull. Even worse,
   changing the ``platform: ...`` in ``./docker-compose*.yml`` requires a ``$ docker
   compose pull ...`` to switch the image. This means pulling again and again some time
   after the push increasingly the likelihood of pulling an image other than the one
   built locally. This leaves a couple options. Parse the build output to extract the
   manifest digest and then use that to retrieve the digests for each platform's image
   and then use those digests in ``./docker-compose*.yml``. Or output the multi-platform
   image to one of the local filesystem formats, figure how to import from there and do
   a similar dance to retrieve and use the digests. This would be fragile and would take
   a lot of work that is likely wasted effort when Docker or someone else provides a
   better way. IOW, these options would mean wastefully fighting tools and frameworks.

   As such, this probably isn't worth the effort until users report significant
   platform-specific bugs.

#. ``py``: Create new branches for different frameworks, e.g.: Flask, Pyramid, Django.
