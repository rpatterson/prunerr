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

   The issues with this is CI resources.  We already exhaust GitLab free CI/CD minutes
   too quickly testing against multiple Python versions.  Actually running the tests in
   ARM images would either consume even more free CI/CD minutes to run on the cloud ARM
   runners or would take forever using emulation in the dedicated project runners, so
   this is unlikely to happen until I start seeing significant platform-specific bugs.
