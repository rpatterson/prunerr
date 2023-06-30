.. SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
..
.. SPDX-License-Identifier: MIT

########################################################################################
Most wanted contributions
########################################################################################

Known bugs and desired features for contributions.

TEMPLATE: remove items your project doesn't care about and add your own.


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

#. `Docker image build-time LABEL's
   <https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys>`_::

     org.opencontainers.image.revision Source control revision identifier for the packaged software.
     org.opencontainers.image.ref.name Name of the reference for a target (string).
     org.opencontainers.image.base.digest Digest of the image this image is based on (string)

#. Container image variants, e.g. slim/alpine:

   I'm increasingly unconvinced this is worth it, so this likely won't happen until I
   hear of a convincing use case.

#. CI/CD for other image platforms:

   One issue with this is CI resources.  We already exhaust GitLab free CI/CD minutes
   too quickly.  Actually running the tests in ARM images would either consume even more
   free CI/CD minutes to run on the cloud ARM runners or would take forever using
   emulation in the dedicated project runners.

   Another issue is lack of important support from Docker.  Docker provides both the
   capability to build images for non-native platforms *and* run images for non-native
   platforms, both albeit slowly via QEMU emulation.  So it seems like we have
   everything we need to build a non-native image, run the tests against it as a check,
   and then publish it once passing.  Unfortunately, Docker doesn't provide local access
   to built multi-platform images, it only supports pushing them to a registry or
   exporting them to some form of filesystem archive.  This means we can't depend on
   subsequent runs of the image tag to be the same image we just built as someone else
   could have pushed another build to the registry between our push and subsequent pull.
   This is made worse given that each time we change the ``platform: ...`` in
   ``./docker-compose*.yml`` requires a ``$ docker compose pull ...`` to switch the
   image so that means we could be pulling again and again some time after the push
   increasingly the likelihood that we end up pulling an image other than the one we
   built.  This leaves us with a couple options.  We could parse the build output to
   extract the manifest digest and then use that to retrieve the digests for each
   platform's image and then use those digests in ``./docker-compose*.yml``.  Or we
   could output the multi-platform image to one of the local filesystem formats, figure
   how to import from there and do the equivalent dance to retrieve and use the digests.
   This would be very fragile and would take a lot of work that is likely to be wasted
   when Docker or someone else provides a better way.  IOW, we would be wastefully
   fighting our tools and frameworks.

   So this is unlikely to happen until I start seeing significant platform-specific bugs.
