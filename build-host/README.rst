##################################################
Project Build Host
##################################################
The container image in which this project is built
**************************************************

This directory is used to build a container image which can be used to build, test and
release this project.  The image can be used in project host platforms to provide CI/CD
and can also be used locally to reproduce CI/CD issues locally.

Changes to this image aren't published as a part of the project release process and as
such project maintainers are responsible for pushing new versions of this image as
changes are made.  This can be done using the project's ``../Makefile``::

  $ cd ..
  $ make bootstrap-project
