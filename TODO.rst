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

#. `Accept project donations <https://itsfoss.com/open-source-funding-platforms/>`_.

#. Container image variants: e.g. slim/alpine

#. `Docker image build-time LABEL's
   <https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys>`_::

     org.opencontainers.image.revision Source control revision identifier for the packaged software.
     org.opencontainers.image.ref.name Name of the reference for a target (string).
     org.opencontainers.image.base.digest Digest of the image this image is based on (string)
     This SHOULD be the immediate image sharing zero-indexed layers with the image, such as from a Dockerfile FROM statement.
     This SHOULD NOT reference any other images used to generate the contents of the image (e.g., multi-stage Dockerfile builds).
     This SHOULD be the immediate image sharing zero-indexed layers with the image, such as from a Dockerfile FROM statement.
     This SHOULD NOT reference any other images used to generate the contents of the image (e.g., multi-stage Dockerfile builds).
     If the image.base.name annotation is specified, the image.base.digest annotation SHOULD be the digest of the manifest referenced by the image.ref.name annotation.

#. Automate submitting merge/pull requests from the ``devel-upgrade-branch`` target.
