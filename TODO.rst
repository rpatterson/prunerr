########################################################################################
Seeking Contributions
########################################################################################

Known bugs and desirable features for which contributions are most welcome.

TEMPLATE: Remove any of the following TODOs from the template that your project doesn't
care about and add your own.


****************************************************************************************
Required
****************************************************************************************


****************************************************************************************
High Priority
****************************************************************************************

#. Any documentation improvements!

   Documentation benefits perhaps most from the attention of fresh eyes.  If you find
   anything confusing, please ask for clarification and once you understand what you
   didn't before, please do contribute changes to the documentation to spare future
   users the same confusion.


****************************************************************************************
Nice to Have
****************************************************************************************

#. Documentation via Sphinx with CI to publish to RTFD.

#. New branches for different frameworks, e.g.: Flask, Pyramid, Django

#. Better release notes content for final releases with no changes since the last
   pre-release.

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
   too quickly testing against multiple Python versions.  Actually running the tests in
   ARM images would either consume even more free CI/CD minutes to run on the cloud ARM
   runners or would take forever using emulation in the dedicated project runners.

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
